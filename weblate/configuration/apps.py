# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConfigurationConfig(AppConfig):
    name = "weblate.configuration"
    label = "configuration"
    verbose_name = _("Weblate configuration")
