# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class GlossaryConfig(AppConfig):
    name = "weblate.glossary"
    label = "glossary"
    verbose_name = gettext_lazy("Glossaries")
