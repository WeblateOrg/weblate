# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unbounded Django reference for small, trusted compatibility fixtures only."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django.core.serializers.json import DjangoJSONEncoder
from django.template import Context, Engine, Library, Template, TemplateSyntaxError
from django.template.defaulttags import do_for
from django.utils.translation import override

from weblate.utils.render_engine import InvalidString


def replace(value: str, char: str, replace_char: str) -> str:
    return value.replace(char, replace_char)


def json_literal(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, cls=DjangoJSONEncoder)


def python_literal(value: object) -> str:
    return repr(json.loads(json_literal(value)))


class ReferenceEngine(Engine):
    default_builtins: ClassVar[list[str]] = [
        "django.template.defaultfilters",
        "weblate.utils.templatetags.safe_render",
    ]

    def get_template_builtins(self, builtins: list[str]) -> list[Library]:
        result = []
        for original in super().get_template_builtins(builtins):
            library = Library()
            library.tags = original.tags.copy()
            library.filters = original.filters.copy()
            if "for" in library.tags:
                library.tags["for"] = do_for
                library.simple_tag(replace)
                library.filter("json", json_literal)
                library.filter("python", python_literal)
            result.append(library)
        return result


def render_reference(source: str, values: dict[str, Any]) -> str:
    try:
        with override("en"):
            return Template(
                source,
                engine=ReferenceEngine(
                    autoescape=False, string_if_invalid=InvalidString("%s")
                ),
            ).render(Context(values.copy(), autoescape=False))
    except Exception as error:
        raise TemplateSyntaxError(str(error)) from error
