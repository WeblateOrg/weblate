# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from types import FunctionType
from typing import TYPE_CHECKING

from weblate.checks.models import CHECKS

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from weblate.trans.models import Unit


def highlight_pygments(source: str, unit: Unit) -> Generator[tuple[int, int, str]]:
    """
    Highlight syntax characters using pygments.

    This is not really a full syntax highlighting, we're only interested in
    non-translatable strings.
    """
    # ruff: ignore[import-outside-top-level]
    from pygments.lexers.markup import RstLexer

    # ruff: ignore[import-outside-top-level]
    from pygments.token import Token

    if "rst-text" in unit.all_flags:
        lexer = RstLexer(stripnl=False)
        start = 0
        for token, text in lexer.get_tokens(source):
            if token == Token.Literal.String:
                if text[0] == "`" and text != "`_":
                    yield (start, start + 1, "`")
                else:
                    yield (start, start + len(text), text)
            elif token == Token.Literal.String.Interpol:
                yield (start, start + len(text), text)
            elif token == Token.Generic.Strong:
                end = start + len(text)
                yield (start, start + 2, "**")
                yield (end - 2, end, "**")
            elif token == Token.Generic.Emph:
                end = start + len(text)
                yield (start, start + 1, "*")
                yield (end - 1, end, "*")
            start += len(text)


def merge_highlight_spans(
    source: str, highlights: list[tuple[int, int, str]]
) -> list[tuple[int, int, str]]:
    """Merge overlapping highlight spans (nested or partial) into their union intervals."""
    merged: list[tuple[int, int, str]] = []
    for start, end, text in highlights:
        if merged and start < merged[-1][1]:
            prev_start, prev_end, _ = merged[-1]
            new_end = max(prev_end, end)
            merged[-1] = (prev_start, new_end, source[prev_start:new_end])
        else:
            merged.append((start, end, text))
    return merged


def highlight_string(
    source: str, unit: Unit, *, highlight_syntax: bool = False
) -> list[tuple[int, int, str]]:
    """Return highlights for a string."""
    if unit is None:
        return []
    highlights = []
    for check in CHECKS:
        if not CHECKS[check].target:
            continue
        highlights.extend(CHECKS[check].check_highlight(source, unit))

    if highlight_syntax:
        highlights.extend(highlight_pygments(source, unit))

    # Remove empty strings
    highlights = [highlight for highlight in highlights if highlight[2]]

    # Sort by order in string, longest first
    highlights.sort(key=lambda item: (item[0], -item[1]))

    return merge_highlight_spans(source, highlights)


def replace_highlighted(
    source: str,
    unit: Unit,
    replacement: str | Callable[[int], str] = "",
    *,
    highlight_syntax: bool = False,
) -> str:
    """Replace highlighted ranges in source string."""
    replacement_key = get_replacement_cache_key(replacement)
    use_cache = unit is not None and replacement_key is not None
    if use_cache:
        cache_key = (
            source,
            replacement_key,
            highlight_syntax,
            get_highlight_cache_context(unit),
        )
        cache = unit.__dict__.setdefault("_replace_highlighted_cache", {})
        if cache_key in cache:
            return cache[cache_key]

    highlights = highlight_string(source, unit, highlight_syntax=highlight_syntax)
    if not highlights:
        if use_cache:
            cache[cache_key] = source
        return source

    result = []
    last_end = 0
    for start, end, _text in highlights:
        if start < last_end:
            last_end = max(last_end, end)
            continue
        result.append(source[last_end:start])
        if callable(replacement):
            result.append(replacement(start))
        else:
            result.append(replacement)
        last_end = end
    result.append(source[last_end:])
    replaced = "".join(result)
    if use_cache:
        cache[cache_key] = replaced
    return replaced


def get_replacement_cache_key(replacement: str | Callable[[int], str]) -> object | None:
    if isinstance(replacement, str):
        return replacement
    if (
        isinstance(replacement, FunctionType)
        and replacement.__name__ != "<lambda>"
        and "<locals>" not in replacement.__qualname__
    ):
        return replacement
    return None


def get_highlight_cache_context(unit: Unit) -> str:
    return unit.all_flags.format()


def placeholder_replacement(start_index: int) -> str:
    return f"x-weblate-{start_index}"
