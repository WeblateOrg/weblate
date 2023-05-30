# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "weblate.integrations"
    label = "integrations"
    verbose_name = "Integrations"
