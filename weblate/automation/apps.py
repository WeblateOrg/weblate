# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class AutomationConfig(AppConfig):
    name = "weblate.automation"
    label = "automation"
    verbose_name = "Automation"
