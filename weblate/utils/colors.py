# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import TextChoices
from django.utils.translation import gettext_lazy


class ColorChoices(TextChoices):
    # Translators: Name of a color
    NAVY = "navy", gettext_lazy("Navy")
    # Translators: Name of a color
    BLUE = "blue", gettext_lazy("Blue")
    # Translators: Name of a color
    AQUA = "aqua", gettext_lazy("Aqua")
    # Translators: Name of a color
    TEAL = "teal", gettext_lazy("Teal")
    # Translators: Name of a color
    OLIVE = "olive", gettext_lazy("Olive")
    # Translators: Name of a color
    GREEN = "green", gettext_lazy("Green")
    # Translators: Name of a color
    LIME = "lime", gettext_lazy("Lime")
    # Translators: Name of a color
    YELLOW = "yellow", gettext_lazy("Yellow")
    # Translators: Name of a color
    ORANGE = "orange", gettext_lazy("Orange")
    # Translators: Name of a color
    RED = "red", gettext_lazy("Red")
    # Translators: Name of a color
    MAROON = "maroon", gettext_lazy("Maroon")
    # Translators: Name of a color
    FUCHSIA = "fuchsia", gettext_lazy("Fuchsia")
    # Translators: Name of a color
    PURPLE = "purple", gettext_lazy("Purple")
    # Translators: Name of a color
    BLACK = "black", gettext_lazy("Black")
    # Translators: Name of a color
    GRAY = "gray", gettext_lazy("Gray")
    # Translators: Name of a color
    SILVER = "silver", gettext_lazy("Silver")
