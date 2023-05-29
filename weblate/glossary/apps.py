# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GlossaryConfig(AppConfig):
    name = "weblate.glossary"
    label = "glossary"
    verbose_name = _("Glossaries")
