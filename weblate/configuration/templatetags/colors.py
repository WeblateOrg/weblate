# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Convert colors between formats."""

from django import template

register = template.Library()


@register.filter
def hex_to_rgb(value):
    return ", ".join(
        map(str, tuple(int(value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)))
    )


@register.filter
def darken(value, amount=0.6):
    """Return a darker shade of the given hex color."""
    channels = (int(value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        *(min(255, max(0, round(channel * amount))) for channel in channels)
    )


@register.filter
def lighten(value, amount=0.4):
    """Return a lighter shade of the given hex color."""
    channels = (int(value.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        *(
            min(255, max(0, round(channel + (255 - channel) * amount)))
            for channel in channels
        )
    )
