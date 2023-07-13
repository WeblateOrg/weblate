# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class LegalConfig(AppConfig):
    name = "weblate.legal"
    label = "legal"
    verbose_name = "Legal"
