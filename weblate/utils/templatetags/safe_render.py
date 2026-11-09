# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os.path
from typing import TYPE_CHECKING

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.template.defaulttags import do_for, do_if

from weblate.utils.render_engine import BoundedForNode, check_replace

if TYPE_CHECKING:
    from django.template.base import Parser, Token

register = template.Library()


@register.simple_tag
def replace(value: str, char: str, replace_char: str) -> str:
    check_replace(value, char, replace_char)
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


@register.tag("for")
def bounded_for(parser: Parser, token: Token) -> BoundedForNode:
    node = do_for(parser, token)
    return BoundedForNode(
        node.loopvars,
        node.sequence,
        node.is_reversed,
        node.nodelist_loop,
        node.nodelist_empty,
    )


@register.filter(name="json")
def json_literal(value: object) -> str:
    """Serialize template data as a JSON literal."""
    return json.dumps(value, ensure_ascii=False, cls=DjangoJSONEncoder)


@register.filter(name="python")
def python_literal(value: object) -> str:
    """Serialize plain template data as a Python literal."""
    return repr(json.loads(json_literal(value)))
