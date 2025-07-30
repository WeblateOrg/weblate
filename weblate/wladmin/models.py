# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TypedDict

import dateutil.parser
from appconf import AppConf
from django.conf import settings
from django.contrib.admin import ModelAdmin
from django.core.cache import cache
from django.core.checks import run_checks
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.trans.models import Component, Project
from weblate.utils.backup import (
    BackupError,
    backup,
    cleanup,
    get_paper_key,
    initialize,
    make_password,
    prune,
)
from weblate.utils.const import SUPPORT_STATUS_CACHE_KEY
from weblate.utils.requests import request
from weblate.utils.site import get_site_url
from weblate.utils.stats import GlobalStats
from weblate.utils.validators import validate_backup_path
from weblate.vcs.ssh import ensure_ssh_key


class WeblateConf(AppConf):
    BACKGROUND_ADMIN_CHECKS = True

    class Meta:
        prefix = ""


class WeblateModelAdmin(ModelAdmin):
    """Customized Model Admin object."""

    delete_confirmation_template = "wladmin/delete_confirmation.html"
    delete_selected_confirmation_template = "wladmin/delete_selected_confirmation.html"


class ConfigurationErrorManager(models.Manager["ConfigurationError"]):
    def configuration_health_check(self, checks=None) -> None:
        # Run deployment checks if needed
        if checks is None:
            checks = run_checks(include_deployment_checks=True)
        checks_dict = {check.id: check for check in checks}
        criticals = {
            "weblate.E002",
            "weblate.E003",
            "weblate.E007",
            "weblate.E009",
            "weblate.E012",
            "weblate.E013",
            "weblate.E014",
            "weblate.E015",
            "weblate.E017",
            "weblate.E018",
            "weblate.E019",
            "weblate.C023",
            "weblate.C029",
            "weblate.C030",
            "weblate.C031",
            "weblate.C032",
            "weblate.E034",
            "weblate.C035",
            "weblate.C036",
            "weblate.C037",
            "weblate.C038",
            "weblate.C040",
            "weblate.C041",
        }
        removals = []
        existing = {error.name: error for error in self.all()}

        for check_id in criticals:
            if check_id in checks_dict:
                check = checks_dict[check_id]
                if check_id in existing:
                    error = existing[check_id]
                    if error.message != check.msg:
                        error.message = check.msg
                        error.save(update_fields=["message"])
                else:
                    self.create(name=check_id, message=check.msg)
            elif check_id in existing:
                removals.append(check_id)

        if removals:
            self.filter(name__in=removals).delete()


class ConfigurationError(models.Model):
    name = models.CharField(unique=True, max_length=150)
    message = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    ignored = models.BooleanField(default=False, db_index=True)

    objects = ConfigurationErrorManager()

    class Meta:
        indexes = [
            models.Index(fields=["ignored", "timestamp"]),
        ]
        verbose_name = "Configuration error"
        verbose_name_plural = "Configuration errors"

    def __str__(self) -> str:
        return self.name


SUPPORT_NAMES = {
    # Translators: The Weblate server has no paid support by the Weblate team
    "community": gettext_lazy("Community support"),
    # Translators: The Weblate server is hosted by the Weblate team
    "hosted": gettext_lazy("Hosted service"),
    # Translators: The Weblate server has paid support from the Weblate team
    "basic": gettext_lazy("Basic self-hosted support"),
    # Translators: The Weblate server has extended support from the Weblate team
    "extended": gettext_lazy("Extended self-hosted support"),
    # Translators: The Weblate server has premium support from the Weblate team
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
    limits = models.JSONField(default=dict)
    has_subscription = models.BooleanField(default=False)
    backup_repository = models.CharField(max_length=500, default="", blank=True)

    objects = SupportStatusManager()

    class Meta:
        verbose_name = "Support status"
        verbose_name_plural = "Support statuses"

    def __str__(self) -> str:
        return f"{self.name}:{self.expiry}"

    def get_verbose(self):
        if self.has_expired_support:
            return gettext("Unpaid subscription")
        return SUPPORT_NAMES.get(self.name, self.name)

    def refresh(self) -> None:
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
        ssh_key = ensure_ssh_key()
        if ssh_key:
            data["ssh_key"] = ssh_key["key"]
        response = request("post", settings.SUPPORT_API_URL, data=data, timeout=360)
        response.raise_for_status()
        payload = response.json()
        self.name = payload["name"]
        self.expiry = dateutil.parser.parse(payload["expiry"])
        self.in_limits = payload["in_limits"]
        self.limits = payload["limits"]
        self.has_subscription = payload["has_subscription"]
        self.backup_repository = payload["backup_repository"]
        if self.backup_repository:
            BackupService.objects.get_or_create(
                repository=self.backup_repository, defaults={"enabled": False}
            )
        # Invalidate support status cache
        cache.delete(SUPPORT_STATUS_CACHE_KEY)

    def get_limits_details(self):
        stats = GlobalStats()
        current_values = {
            "hosted_words": stats.all_words,
            "hosted_strings": stats.all,
            "source_strings": stats.source_strings,
            "projects": Project.objects.count(),
            "languages": stats.languages,
        }
        names = {
            "hosted_words": gettext_lazy("Hosted words"),
            "hosted_strings": gettext_lazy("Hosted strings"),
            "source_strings": gettext_lazy("Source strings"),
            "projects": gettext_lazy("Projects"),
            "languages": gettext_lazy("Languages"),
        }
        result = []
        for limit, value in self.limits.items():
            if not value or limit not in names:
                continue
            current = current_values[limit]
            result.append(
                {
                    "name": names[limit],
                    "limit": value,
                    "current": current,
                    "in_limit": current < value,
                }
            )
        return result

    @property
    def has_support(self) -> bool:
        return self.name != "community"

    @property
    def has_expired_support(self) -> bool:
        return self.pk is not None and self.has_subscription and not self.has_support


class BackupService(models.Model):
    repository = models.CharField(
        max_length=500,
        default="",
        verbose_name=gettext_lazy("Backup repository URL"),
        help_text=gettext_lazy(
            "Use /path/to/repo for local backups "
            "or user@host:/path/to/repo "
            "or ssh://user@host:port/path/to/backups for remote SSH backups."
        ),
        validators=[validate_backup_path],
    )
    enabled = models.BooleanField(default=True)
    timestamp = models.DateTimeField(default=timezone.now)
    passphrase = models.CharField(max_length=100, default=make_password)
    paperkey = models.TextField()

    class Meta:
        verbose_name = "Support service"
        verbose_name_plural = "Support services"

    def __str__(self) -> str:
        return self.repository

    @cached_property
    def last_logs(self) -> models.QuerySet[BackupLog]:
        return self.backuplog_set.order_by("-timestamp")[:10]

    @cached_property
    def has_errors(self) -> bool:
        for log in self.last_logs:
            if log.event == "error":
                return True
            if log.event == "backup":
                return False
        return False

    def ensure_init(self) -> None:
        if not self.paperkey:
            try:
                self.paperkey = get_paper_key(self.repository)
                self.save(update_fields=["paperkey"])
            except BackupError:
                try:
                    log = initialize(self.repository, self.passphrase)
                    self.backuplog_set.create(event="init", log=log)
                    self.paperkey = get_paper_key(self.repository)
                    self.save()
                except BackupError as error:
                    self.backuplog_set.create(event="error", log=str(error))

    def backup(self) -> None:
        try:
            log = backup(self.repository, self.passphrase)
            self.backuplog_set.create(event="backup", log=log)
        except BackupError as error:
            self.backuplog_set.create(event="error", log=str(error))

    def prune(self) -> None:
        try:
            log = prune(self.repository, self.passphrase)
            self.backuplog_set.create(event="prune", log=log)
        except BackupError as error:
            self.backuplog_set.create(event="error", log=str(error))

    def cleanup(self) -> None:
        initial = self.backuplog_set.filter(event="cleanup").exists()
        try:
            log = cleanup(self.repository, self.passphrase, initial=initial)
            self.backuplog_set.create(event="cleanup", log=log)
        except BackupError as error:
            self.backuplog_set.create(event="error", log=str(error))


class BackupLog(models.Model):
    service = models.ForeignKey(BackupService, on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    event = models.CharField(
        max_length=100,
        choices=(
            # Translators: Backup repository operation
            ("backup", gettext_lazy("Backup performed")),
            # Translators: Backup repository operation
            ("error", gettext_lazy("Backup failed")),
            # Translators: Backup repository operation
            ("prune", gettext_lazy("Deleted the oldest backups")),
            # Translators: Backup repository operation
            ("cleanup", gettext_lazy("Cleaned up backup storage")),
            # Translators: Backup repository operation
            ("init", gettext_lazy("Repository initialization")),
        ),
        db_index=True,
    )
    log = models.TextField()

    class Meta:
        verbose_name = "Backup log"
        verbose_name_plural = "Backup logs"

    def __str__(self) -> str:
        return f"{self.service}:{self.event}"


class SupportStatusDict(TypedDict):
    has_support: bool
    in_limits: bool
    has_expired_support: bool
    backup_repository: str
    name: str
    is_hosted_weblate: bool
    is_dedicated: bool


def get_support_status(request: AuthenticatedHttpRequest) -> SupportStatusDict:
    support_status: SupportStatusDict
    if hasattr(request, "weblate_support_status"):
        support_status = request.weblate_support_status
    else:
        support_status = cache.get(SUPPORT_STATUS_CACHE_KEY)
        if support_status is None:
            support_status_instance = SupportStatus.objects.get_current()
            is_hosted = support_status_instance.name == "hosted"
            support_status = {
                "name": support_status_instance.name,
                "is_hosted_weblate": is_hosted
                and settings.SITE_DOMAIN == "hosted.weblate.org",
                "is_dedicated": is_hosted,
                "has_support": support_status_instance.has_support,
                "has_expired_support": support_status_instance.has_expired_support,
                "in_limits": support_status_instance.in_limits,
                "backup_repository": support_status_instance.backup_repository,
            }
            cache.set(SUPPORT_STATUS_CACHE_KEY, support_status, 86400)
        request.weblate_support_status = support_status
    return support_status
