# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TransConfig(AppConfig):
    name = "weblate.trans"
    label = "trans"
    verbose_name = _("Weblate translations")
