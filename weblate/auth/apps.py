# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AuthConfig(AppConfig):
    name = "weblate.auth"
    label = "weblate_auth"
    verbose_name = "Authentication"

    def ready(self) -> None:
        from weblate.auth.models import sync_create_groups

        post_migrate.connect(sync_create_groups, sender=self)
