# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bounded template compilation and per-render work limits."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Never

if TYPE_CHECKING:
    from collections.abc import Callable

from django.template import TemplateSyntaxError
from django.utils.text import smart_split
from django.utils.translation import gettext

from weblate.utils.render_limits import DEPTH_LIMIT

FILTER_LIMIT = 1024
OPERATION_LIMIT = 8192
WORK_LIMIT = 8 * 1024 * 1024
PARSE_WORK_LIMIT = 8 * 1024 * 1024
TOKEN_LIMIT = 1024
TOKEN_SIZE_LIMIT = 2048
CONDITION_TERM_LIMIT = 64
OPENING = re.compile(r"{{|{%|{#")


class TemplateDiagnosticError(TemplateSyntaxError):
    """A bounded-render failure. Only validation may include source details."""


TEMPLATE_TAGS = frozenset(
    {"if", "elif", "else", "endif", "for", "empty", "endfor", "replace"}
)


def count_filters(contents: str) -> int:
    """Count separators outside quoted literals in one bounded token."""
    quote = None
    escaped = False
    count = 0
    for index, char in enumerate(contents):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "|":
            count += 1
        elif char == "{" and contents[index : index + 2] in {"{{", "{%", "{#"}:
            raise TemplateDiagnosticError(
                gettext("Nested template delimiters are not supported.")
            )
    return count


def preflight(source: str, *, for_validation: bool = False) -> None:
    """Conservatively bound Django parsing without interpreting expressions."""
    position = tokens = separators = work = 0
    stack: list[tuple[str, int]] = []

    def fail(message: str, offset: int) -> Never:
        error = TemplateDiagnosticError(message)
        error.__dict__["render_location"] = (source.count("\n", 0, offset) + 1, None)
        raise error

    while match := OPENING.search(source, position):
        start = match.start()
        opening = match.group()
        closing = {"{{": "}}", "{%": "%}", "{#": "#}"}[opening]
        end = source.find(closing, start + 2)
        if end == -1:
            fail(gettext("Unclosed template token."), start)
        contents = source[start + 2 : end]
        if len(contents) > TOKEN_SIZE_LIMIT:
            fail(
                gettext("Template token exceeds the size limit of %(limit)d bytes.")
                % {"limit": TOKEN_SIZE_LIMIT},
                start,
            )
        if "\n" in contents:
            fail(gettext("Template tokens cannot span multiple lines."), start)
        size = len(contents.encode("utf-8"))
        tokens += 1 + (start > position)
        try:
            separators += count_filters(contents) if opening != "{#" else 0
        except TemplateDiagnosticError as error:
            fail(str(error), start)
        work += size * size
        if size > TOKEN_SIZE_LIMIT:
            fail(
                gettext("Template token exceeds the size limit of %(limit)d bytes.")
                % {"limit": TOKEN_SIZE_LIMIT},
                start,
            )
        if tokens > TOKEN_LIMIT:
            fail(
                gettext("Template exceeds the parsing limit of %(limit)d tokens.")
                % {"limit": TOKEN_LIMIT},
                start,
            )
        if separators > FILTER_LIMIT:
            fail(
                gettext("Template exceeds the parsing limit of %(limit)d filters.")
                % {"limit": FILTER_LIMIT},
                start,
            )
        if work > PARSE_WORK_LIMIT:
            fail(
                gettext("Template exceeds the parsing work limit of %(limit)d units.")
                % {"limit": PARSE_WORK_LIMIT},
                start,
            )
        if opening == "{%":
            check_tag(contents, stack, start, fail, for_validation=for_validation)
        position = end + 2
    if stack:
        tag, start = stack[-1]
        fail(gettext('Unclosed template tag "%(tag)s".') % {"tag": tag}, start)
    if tokens + (position < len(source)) > TOKEN_LIMIT:
        fail(
            gettext("Template exceeds the parsing limit of %(limit)d tokens.")
            % {"limit": TOKEN_LIMIT},
            position,
        )


def check_tag(
    contents: str,
    stack: list[tuple[str, int]],
    start: int,
    fail: Callable[[str, int], Never],
    *,
    for_validation: bool = False,
) -> None:
    terms = list(smart_split(contents))
    if not terms:
        fail(gettext("Template tag is empty."), start)
    tag = terms[0]
    if tag in {"if", "elif"} and len(terms) > CONDITION_TERM_LIMIT:
        fail(
            gettext("Condition exceeds the parsing limit of %(limit)d terms.")
            % {"limit": CONDITION_TERM_LIMIT},
            start,
        )
    if tag in {"if", "for"}:
        stack.append((tag, start))
        if len(stack) > DEPTH_LIMIT:
            fail(
                gettext("Template exceeds the nesting limit of %(limit)d levels.")
                % {"limit": DEPTH_LIMIT},
                start,
            )
    elif tag in {"endif", "endfor"}:
        if not stack or stack.pop()[0] != tag[3:]:
            fail(
                gettext('Unexpected closing tag "%(tag)s".') % {"tag": tag},
                start,
            )
    elif tag in {"else", "elif", "empty"}:
        expected = "for" if tag == "empty" else "if"
        if not stack or stack[-1][0] != expected:
            fail(
                gettext('Tag "%(tag)s" requires an enclosing "%(parent)s" tag.')
                % {"tag": tag, "parent": expected},
                start,
            )
    elif tag != "replace":
        if for_validation:
            fail(gettext('Unsupported template tag "%(tag)s".') % {"tag": tag}, start)
        fail(gettext("Unsupported template tag."), start)
