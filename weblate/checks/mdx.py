# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weblate.trans.models import Unit

# Various lexical contexts tracked while scanning a JSX expression.
_CODE = 0
_SINGLE = 1  # '...'
_DOUBLE = 2  # "..."
_TEMPLATE = 3  # `...`
_LINE_COMMENT = 4  # // ...
_BLOCK_COMMENT = 5  # /* ... */
_REGEX = 6  # /.../

# Characters after which a ``/`` starts a regex literal. Includes ``>`` so that
# a regex following an arrow (``=>``) or a ``>`` comparison is recognized rather
# than parsed as division. ``<`` is intentionally excluded because ``</tag>``
# JSX closing tags would otherwise be misread as regex literals.
_REGEX_PRECEDERS = frozenset("(,=:[{;!&|?+-*%~^>")


def _regex_allowed(prev: str) -> bool:
    """Decide whether a ``/`` begins a regex based on the previous code char."""
    return not prev or prev in _REGEX_PRECEDERS


def _scan_expression(text: str, start: int) -> int | None:  # noqa: C901
    """
    Find the closing brace of the JSX expression opening at ``start``.

    Returns the index of closing brace or None if the expression is unterminated.
    """
    length = len(text)
    depth = 1
    mode = _CODE
    # Mode to restore when a ``}`` closes; lets ``${ ... }`` interpolations
    # return to template context. Length is always ``depth - 1``.
    restore: list[int] = []
    in_char_class = False  # whether the current regex is inside ``[...]``
    prev = ""  # last significant character
    i = start + 1

    while i < length:
        char = text[i]

        if mode == _CODE:
            if char == "{":
                depth += 1
                restore.append(_CODE)
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return i
                mode = restore.pop()
            elif char == '"':
                mode = _DOUBLE
            elif char == "'":
                mode = _SINGLE
            elif char == "`":
                mode = _TEMPLATE
            elif char == "/" and i + 1 < length and text[i + 1] == "/":
                mode = _LINE_COMMENT
                i += 1
            elif char == "/" and i + 1 < length and text[i + 1] == "*":
                mode = _BLOCK_COMMENT
                i += 1
            elif char == "/" and _regex_allowed(prev):
                mode = _REGEX
                in_char_class = False
            if not char.isspace():
                prev = char

        elif mode == _DOUBLE:
            if char == "\\":
                i += 1
            elif char == '"':
                mode = _CODE
                prev = char

        elif mode == _SINGLE:
            if char == "\\":
                i += 1
            elif char == "'":
                mode = _CODE
                prev = char

        elif mode == _TEMPLATE:
            if char == "\\":
                i += 1
            elif char == "`":
                mode = _CODE
                prev = char
            elif char == "$" and i + 1 < length and text[i + 1] == "{":
                depth += 1
                restore.append(_TEMPLATE)
                mode = _CODE
                i += 1

        elif mode == _LINE_COMMENT:
            if char == "\n":
                mode = _CODE

        elif mode == _BLOCK_COMMENT:
            if char == "*" and i + 1 < length and text[i + 1] == "/":
                mode = _CODE
                i += 1

        elif mode == _REGEX:
            if char == "\\":
                i += 1
            elif char == "[":
                in_char_class = True
            elif char == "]":
                in_char_class = False
            elif char == "/" and not in_char_class:
                mode = _CODE
                prev = char

        i += 1

    return None


def _skip_code_span(text: str, start: int) -> int | None:
    """
    Find the end of the Markdown inline code span opening at ``start``.

    Returns the index of closing backtick or None if there is no matching closing run.
    """
    length = len(text)
    run_end = start
    while run_end < length and text[run_end] == "`":
        run_end += 1
    run = run_end - start

    i = run_end
    while i < length:
        if text[i] == "`":
            close_end = i
            while close_end < length and text[close_end] == "`":
                close_end += 1
            if close_end - i == run:
                return close_end - 1
            i = close_end
        else:
            i += 1

    return None


class SafeMDXCheck(TargetCheck):
    """Check for unsafe MDX content."""

    check_id = "safe-mdx"
    name = gettext_lazy("Safe MDX")
    description = gettext_lazy(
        "JSX expressions in the translation do not match the source."
    )
    default_disabled = True
    version_added = "2026.7"

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Check the target has the same JSX expressions as the source."""
        expected = list(self.get_jsx_expression_matches(source))
        found = list(self.get_jsx_expression_matches(target))
        return sorted(found) != sorted(expected)

    def get_jsx_expression_matches(self, text: str) -> Iterator[str]:
        i = 0
        length = len(text)
        while i < length:
            char = text[i]
            if char == "\\":
                # escaped character can be skipped (e.g. ``\{``)
                i += 2
                continue
            if char == "`":
                # Markdown inline code span
                close = _skip_code_span(text, i)
                if close is not None:
                    i = close + 1
                    continue
            if char == "{":
                # JSX expression
                close = _scan_expression(text, i)
                if close is not None:
                    yield text[i : close + 1]
                    i = close + 1
                    continue
            i += 1
