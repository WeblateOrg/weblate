# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import CheckMessage, Info, register

from weblate.utils.checks import weblate_check
from weblate.wladmin.sites import patch_admin_site

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

patch_admin_site()


class WLAdminConfig(AppConfig):
    name = "weblate.wladmin"
    label = "wladmin"
    verbose_name = "Weblate Admin Extensions"


@register(deploy=True)
def check_backups(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    from weblate.wladmin.models import BackupService

    errors = []
    if not BackupService.objects.filter(enabled=True).exists():
        errors.append(
            weblate_check(
                "weblate.I028",
                "Backups are not configured, "
                "it is highly recommended for production use",
                Info,
            )
        )
    for service in BackupService.objects.filter(enabled=True):
        try:
            last_obj = service.last_logs()[0]
            last_event = last_obj.event
            last_log = last_obj.log
        except IndexError:
            last_event = "error"
            last_log = "missing"
        if last_event == "error":
            errors.append(
                weblate_check(
                    "weblate.C029",
                    f"There was error while performing backups: {last_log}",
                )
            )
            break

    return errors
