# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import template

register = template.Library()


@register.filter
def split(value, key):
    """Split the string by the given key."""
    return value.split(key)
