# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from weblate.utils.errors import report_error

register = template.Library()

CACHE: dict[str, str] = {}

SPIN = '<span class="icon-spin" {} {}>{}</span>'


@register.simple_tag()
def icon(name):
    """
    Inlines SVG icon.

    Inlining is necessary to be able to apply CSS styles on the path.
    """
    if not name:
        raise ValueError("Empty icon name")

    if name not in CACHE:
        if name.startswith("state/"):
            icon_file = os.path.join(settings.STATIC_ROOT, name)
        else:
            icon_file = os.path.join(settings.STATIC_ROOT, "icons", name)
        try:
            with open(icon_file) as handle:
                CACHE[name] = mark_safe(handle.read())  # noqa: S308
        except OSError:
            report_error("Could not load icon")
            return ""

    return CACHE[name]


@register.simple_tag()
def loading_icon(name=None, hidden=True):
    return format_html(
        SPIN,
        format_html('id="loading-{}"', name) if name else "",
        mark_safe('style="display: none"') if hidden else "",  # noqa: S308
        icon("loading.svg"),
    )
