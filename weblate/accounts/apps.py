# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.core.checks import register

from weblate.accounts.checks import check_avatars


class AccountsConfig(AppConfig):
    name = "weblate.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self):
        super().ready()
        register(check_avatars, deploy=True)
