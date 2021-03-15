#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import json

import dateutil.parser
from django.conf import settings
from django.contrib.admin import ModelAdmin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.auth.models import User
from weblate.trans.models import Component, Project
from weblate.utils.backup import (
    BackupError,
    backup,
    get_paper_key,
    initialize,
    make_password,
    prune,
)
from weblate.utils.requests import request
from weblate.utils.site import get_site_url
from weblate.utils.stats import GlobalStats
from weblate.vcs.ssh import generate_ssh_key, get_key_data


class WeblateModelAdmin(ModelAdmin):
    """Customized Model Admin object."""

    delete_confirmation_template = "wladmin/delete_confirmation.html"
    delete_selected_confirmation_template = "wladmin/delete_selected_confirmation.html"


class ConfigurationError(models.Model):
    name = models.CharField(unique=True, max_length=150)
    message = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    ignored = models.BooleanField(default=False, db_index=True)

    class Meta:
        index_together = [("ignored", "timestamp")]

    def __str__(self):
        return self.name


SUPPORT_NAMES = {
    "community": gettext_lazy("Community support"),
    "hosted": gettext_lazy("Hosted service"),
    "basic": gettext_lazy("Basic self-hosted support"),
    "extended": gettext_lazy("Extended self-hosted support"),
    "premium": gettext_lazy("Premium self-hosted support"),
}


class SupportStatusManager(models.Manager):
    def get_current(self):
        try:
            return self.latest("expiry")
        except SupportStatus.DoesNotExist:
            return SupportStatus(name="community")


class SupportStatus(models.Model):
    name = models.CharField(max_length=150)
    secret = models.CharField(max_length=400)
    expiry = models.DateTimeField(db_index=True, null=True)
    in_limits = models.BooleanField(default=True)
    discoverable = models.BooleanField(default=False)

    objects = SupportStatusManager()

    def __str__(self):
        return f"{self.name}:{self.expiry}"

    def get_verbose(self):
        return SUPPORT_NAMES.get(self.name, self.name)

    def refresh(self):
        stats = GlobalStats()
        data = {
            "secret": self.secret,
            "site_url": get_site_url(),
            "site_title": settings.SITE_TITLE,
            "users": User.objects.count(),
            "projects": Project.objects.count(),
            "components": Component.objects.count(),
            "languages": stats.languages,
            "source_strings": stats.source_strings,
            "strings": stats.all,
            "words": stats.all_words,
        }
        if self.discoverable:
            data["discoverable"] = 1
            data["public_projects"] = json.dumps(
                [
                    {
                        "name": project.name,
                        "url": project.get_absolute_url(),
                        "web": project.web,
                    }
                    for project in Project.objects.filter(
                        access_control=Project.ACCESS_PUBLIC
                    ).iterator()
                ]
            )
        ssh_key = get_key_data()
        if not ssh_key:
            generate_ssh_key(None)
            ssh_key = get_key_data()
        if ssh_key:
            data["ssh_key"] = ssh_key["key"]
        response = request("post", settings.SUPPORT_API_URL, data=data)
        response.raise_for_status()
        payload = response.json()
        self.name = payload["name"]
        self.expiry = dateutil.parser.parse(payload["expiry"])
        self.in_limits = payload["in_limits"]
        if payload["backup_repository"]:
            BackupService.objects.get_or_create(
                repository=payload["backup_repository"], defaults={"enabled": False}
            )


class BackupService(models.Model):
    repository = models.CharField(
        max_length=500,
        default="",
        verbose_name=gettext_lazy("Backup repository URL"),
        help_text=gettext_lazy(
            "Use /path/to/repo for local backups "
            "or user@host:/path/to/repo for remote SSH backups."
        ),
    )
    enabled = models.BooleanField(default=True)
    timestamp = models.DateTimeField(default=timezone.now)
    passphrase = models.CharField(max_length=100, default=make_password)
    paperkey = models.TextField()

    def __str__(self):
        return self.repository

    def last_logs(self):
        return self.backuplog_set.order_by("-timestamp")[:10]

    def ensure_init(self):
        if not self.paperkey:
            log = initialize(self.repository, self.passphrase)
            self.backuplog_set.create(event="init", log=log)
            self.paperkey = get_paper_key(self.repository)
            self.save()

    def backup(self):
        try:
            log = backup(self.repository, self.passphrase)
            self.backuplog_set.create(event="backup", log=log)
        except BackupError as error:
            self.backuplog_set.create(event="error", log=str(error))

    def prune(self):
        try:
            log = prune(self.repository, self.passphrase)
            self.backuplog_set.create(event="prune", log=log)
        except BackupError as error:
            self.backuplog_set.create(event="error", log=str(error))


class BackupLog(models.Model):
    service = models.ForeignKey(BackupService, on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    event = models.CharField(
        max_length=100,
        choices=(
            ("backup", gettext_lazy("Backup performed")),
            ("error", gettext_lazy("Backup failed")),
            ("prune", gettext_lazy("Deleted the oldest backups")),
            ("init", gettext_lazy("Repository initialization")),
        ),
    )
    log = models.TextField()

    def __str__(self):
        return f"{self.service}:{self.event}"
