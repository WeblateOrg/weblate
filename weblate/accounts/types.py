# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db.models import TextChoices
from django.utils.translation import pgettext_lazy


class ThemeChoices(TextChoices):
    AUTO = "auto", pgettext_lazy("Theme selection", "Sync with system")
    LIGHT = "light", pgettext_lazy("Theme selection", "Light")
    DARK = "dark", pgettext_lazy("Theme selection", "Dark")
