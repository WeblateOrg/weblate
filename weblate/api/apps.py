# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "weblate.api"
    label = "api"
    verbose_name = "API"
