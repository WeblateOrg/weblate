# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class ChecksConfig(AppConfig):
    name = "weblate.checks"
    label = "checks"
    verbose_name = "Checks"
