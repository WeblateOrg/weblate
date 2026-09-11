# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path

from django import template
from django.template.defaulttags import do_for, do_if

register = template.Library()


@register.simple_tag
def replace(value: str, char: str, replace_char: str) -> str:
    return value.replace(char, replace_char)


@register.filter
def dirname(value: str) -> str:
    return os.path.dirname(value)


@register.filter
def stripext(value: str) -> str:
    return os.path.splitext(value)[0]


@register.filter
def parentdir(value: str) -> str:
    return value.split("/", 1)[-1]


register.tag("if")(do_if)
register.tag("for")(do_for)
