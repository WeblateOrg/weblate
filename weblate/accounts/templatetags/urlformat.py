# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provide user friendly names for social authentication methods."""

from django import template

register = template.Library()


@register.filter
def urlformat(content: str) -> str:
    """Nicely formats URL for display."""
    simplified = content.split("://", 1)[-1].strip("/")
    if len(simplified) > 40:
        return simplified.split("/", 1)[0]
    return simplified
