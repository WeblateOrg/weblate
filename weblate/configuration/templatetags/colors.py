# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"Convert colors between formats"

from django import template

register = template.Library()

@register.filter
def hex_to_rgb(value):
    return ", ".join(map(str, tuple(int(value.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))))
