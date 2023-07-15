# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class MemoryConfig(AppConfig):
    name = "weblate.memory"
    label = "memory"
    verbose_name = "Translation Memory"
