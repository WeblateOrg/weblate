# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.core.checks import register

from weblate.fonts.utils import check_fonts


class FontsConfig(AppConfig):
    name = "weblate.fonts"
    label = "fonts"
    verbose_name = "Fonts"

    def ready(self):
        super().ready()
        register(check_fonts)
