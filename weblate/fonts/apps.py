# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.apps import AppConfig
from django.core.checks import register

from weblate.utils.checks import weblate_check

from .utils import render_size


@register
def check_fonts(app_configs=None, **kwargs):
    """Checks font rendering."""
    try:
        render_size(text="test")
    except Exception as error:
        return [weblate_check("weblate.C024", f"Could not use Pango: {error}")]
    return []


class FontsConfig(AppConfig):
    name = "weblate.fonts"
    label = "fonts"
    verbose_name = "Fonts"
