# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class TransConfig(AppConfig):
    name = "weblate.trans"
    label = "trans"
    verbose_name = gettext_lazy("Weblate translations")
