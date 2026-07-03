# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from itertools import zip_longest
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.checks.base import TargetCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weblate.trans.models import Unit

_JSX_TAG_NAME_RE = re.compile(r"[$_A-Za-z][\w.$:-]*")
_ATTR_NAME_RE = re.compile(r"([A-Za-z_:][\w:.-]*)\s*=\s*$")

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


def _scan_jsx_tag(
    text: str, start: int, limit: int | None = None
) -> tuple[bool, str, bool, int | None] | None:
    """Scan a JSX tag starting at ``start``."""
    length = len(text) if limit is None else min(limit, len(text))
    if text[start] != "<" or start + 1 >= len(text):
        return None

    i = start + 1
    closing = text[i] == "/"
    if closing:
        i += 1

    tag_match = _JSX_TAG_NAME_RE.match(text, i)
    if tag_match is None:
        return None

    tag = tag_match.group()
    quote = ""
    i = tag_match.end()
    while i < length:
        char = text[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == quote:
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == "{":
            close = _scan_expression(text, i)
            if close is None or close >= length:
                return (closing, tag, False, None)
            i = close
        elif char == ">":
            self_closing = not closing and text[start + 1 : i].rstrip().endswith("/")
            return (closing, tag, self_closing, i)
        elif char == "<":
            return None
        i += 1

    return (closing, tag, False, None)


def _iter_jsx_tags(text: str) -> Iterator[tuple[bool, str, bool]]:
    """Yield closed JSX tags while ignoring expressions and code spans."""
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "`":
            close = _skip_code_span(text, i)
            if close is not None:
                i = close + 1
                continue
        if char == "{":
            close = _scan_expression(text, i)
            if close is not None:
                i = close + 1
                continue
        if char == "<":
            tag = _scan_jsx_tag(text, i)
            if tag is not None:
                closing, tag_name, self_closing, end = tag
                if end is None:
                    break
                yield closing, tag_name, self_closing
                i = end + 1
                continue
        i += 1


def _find_unclosed_jsx_tag(text: str, start: int) -> tuple[int, str] | None:
    """Find an opening JSX tag containing ``start``."""
    i = 0
    while i < start:
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "`":
            close = _skip_code_span(text, i)
            if close is not None and close < start:
                i = close + 1
                continue
        if char == "{":
            close = _scan_expression(text, i)
            if close is not None and close < start:
                i = close + 1
                continue
        if char == "<":
            tag = _scan_jsx_tag(text, i, start)
            if tag is not None:
                closing, tag_name, _self_closing, end = tag
                if end is None:
                    if closing:
                        return None
                    return (i, tag_name)
                i = end + 1
                continue
        i += 1

    return None


def _is_attribute_name_char(char: str) -> bool:
    """Return whether char is allowed after the first JSX attribute name char."""
    return char.isalnum() or char in "_:.-"


def _find_attribute_name(text: str, equals: int) -> str | None:
    """Find the JSX attribute name before an equals sign."""
    i = equals - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    end = i + 1
    while i >= 0 and _is_attribute_name_char(text[i]):
        i -= 1
    if end == i + 1:
        return None
    name = text[i + 1 : end]
    if name[0].isalpha() or name[0] in "_:":
        return name
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
        missing = object()
        return any(
            expected != found
            for expected, found in zip_longest(
                self.get_jsx_expression_signatures(source),
                self.get_jsx_expression_signatures(target),
                fillvalue=missing,
            )
        )

    def get_jsx_expression_signatures(  # noqa: C901
        self, text: str
    ) -> Iterator[tuple[str, str, tuple[str, ...], str]]:
        """Extract JSX expressions together with their syntactic context."""
        stack: list[str] = []
        open_tag: tuple[int, bool, str, bool, int | None] | None = None
        pending_attr: str | None = None
        quote = ""
        i = 0
        length = len(text)
        while i < length:
            char = text[i]

            if open_tag is not None:
                _tag_start, closing, tag, self_closing, end = open_tag
                if quote:
                    if char == "\\":
                        i += 2
                        continue
                    if char == quote:
                        quote = ""
                elif char in {'"', "'"}:
                    quote = char
                elif char == "=":
                    pending_attr = _find_attribute_name(text, i)
                elif char == "{":
                    close = _scan_expression(text, i)
                    if close is not None:
                        tag_stack = (*tuple(stack), tag)
                        if pending_attr is None:
                            yield ("tag", "", tag_stack, text[i : close + 1])
                        else:
                            yield (
                                "attribute",
                                pending_attr,
                                tag_stack,
                                text[i : close + 1],
                            )
                            pending_attr = None
                        i = close + 1
                        continue
                elif i == end and char == ">":
                    if closing:
                        for index in range(len(stack) - 1, -1, -1):
                            if stack[index] == tag:
                                del stack[index:]
                                break
                    elif not self_closing:
                        stack.append(tag)
                    open_tag = None
                    pending_attr = None
                i += 1
                continue

            if char == "\\":
                i += 2
                continue
            if char == "`":
                close = _skip_code_span(text, i)
                if close is not None:
                    i = close + 1
                    continue
            if char == "<":
                scanned = _scan_jsx_tag(text, i)
                if scanned is not None:
                    closing, tag, self_closing, end = scanned
                    open_tag = (i, closing, tag, self_closing, end)
                    i += 1
                    continue
            if char == "{":
                close = _scan_expression(text, i)
                if close is not None:
                    yield ("text", "", tuple(stack), text[i : close + 1])
                    i = close + 1
                    continue
            i += 1

    def get_jsx_expression_context(
        self, text: str, start: int
    ) -> tuple[str, str, tuple[str, ...]]:
        """Return whether an expression appears in JSX text or an attribute."""
        stack = self.get_jsx_element_stack(text[:start])
        tag_context = _find_unclosed_jsx_tag(text, start)
        if tag_context is not None:
            tag_start, tag = tag_context
            before_expression = text[tag_start + 1 : start]
            tag_stack = (*stack, tag)
            attr_match = _ATTR_NAME_RE.search(before_expression)
            if attr_match:
                return ("attribute", attr_match.group(1), tag_stack)
            return ("tag", "", tag_stack)
        return ("text", "", stack)

    def get_jsx_element_stack(self, text: str) -> tuple[str, ...]:
        """Return a best-effort stack of JSX elements open at the end of text."""
        stack: list[str] = []
        for closing, tag, self_closing in _iter_jsx_tags(text):
            if closing:
                for index in range(len(stack) - 1, -1, -1):
                    if stack[index] == tag:
                        del stack[index:]
                        break
            elif not self_closing:
                stack.append(tag)
        return tuple(stack)

    def get_jsx_expression_matches(self, text: str) -> Iterator[str]:
        for _start, expression in self._iter_jsx_expressions(text):
            yield expression

    def _iter_jsx_expressions(self, text: str) -> Iterator[tuple[int, str]]:
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
                    yield i, text[i : close + 1]
                    i = close + 1
                    continue
            i += 1
