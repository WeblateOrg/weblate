# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
from __future__ import unicode_literals

from django.apps import AppConfig
from django.core.checks import Critical, Info, register

from weblate.utils.docs import get_doc_url


class WLAdminConfig(AppConfig):
    name = "weblate.wladmin"
    label = "wladmin"
    verbose_name = "Weblate Admin Extensions"

    def ready(self):
        super(WLAdminConfig, self).ready()
        register(check_backups, deploy=True)


def check_backups(app_configs, **kwargs):
    from weblate.wladmin.models import BackupService

    errors = []
    if not BackupService.objects.filter(enabled=True).exists():
        errors.append(
            Info(
                "Backups are not configured, "
                "it is highly recommended for production use",
                hint=get_doc_url("admin/backup"),
                id="weblate.I028",
            )
        )
    for service in BackupService.objects.filter(enabled=True):
        try:
            last_log = service.last_logs()[0].event
        except IndexError:
            last_log = "error"
        if last_log == "error":
            errors.append(
                Critical(
                    "There was error while performing backups: {}".format(last_log.log),
                    hint=get_doc_url("admin/backup"),
                    id="weblate.C029",
                )
            )
            break

    return errors
