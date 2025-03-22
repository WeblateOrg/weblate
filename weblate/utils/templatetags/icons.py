# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from weblate.utils.icons import load_icon

register = template.Library()

ICONS_CACHE: dict[str, str] = {}

SPIN = '<span class="icon-spin" {} {}>{}</span>'


@register.simple_tag
def icon(name: str) -> str:
    """
    Inlines SVG icon.

    Inlining is necessary to be able to apply CSS styles on the path.
    """
    return mark_safe(load_icon(name).decode())  # noqa: S308


@register.simple_tag
def loading_icon(name=None, hidden=True):
    return format_html(
        SPIN,
        format_html('id="loading-{}"', name) if name else "",
        mark_safe('style="display: none"') if hidden else "",
        icon("loading.svg"),
    )
