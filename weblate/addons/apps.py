# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class AddonsConfig(AppConfig):
    name = "weblate.addons"
    label = "addons"
    verbose_name = "Add-ons"
