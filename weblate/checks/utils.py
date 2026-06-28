# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from types import FunctionType
from typing import TYPE_CHECKING

from weblate.checks.base import Highlight
from weblate.checks.models import CHECKS

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from weblate.trans.models import Unit

MARKUP_TAG_RE = re.compile(
    r"^(?:<|&lt;)\s*(?P<closing>/)?\s*"
    r"(?P<tag>[A-Za-z][\w:.-]*)"
    r"(?P<body>.*?)(?:>|&gt;)$"
)
BBCODE_TAG_RE = re.compile(
    r"^\[\s*(?P<closing>/)?\s*(?P<tag>[A-Za-z][\w:.-]*)(?P<body>.*?)\]$"
)


def _get_markup_tag(highlight: Highlight) -> tuple[str, bool, bool] | None:
    for regexp in (MARKUP_TAG_RE, BBCODE_TAG_RE):
        match = regexp.match(highlight.text)
        if match is None:
            continue
        body = match.group("body").strip()
        return (
            match.group("tag").lower(),
            bool(match.group("closing")),
            body.endswith("/"),
        )
    return None


def pair_markup_highlights(
    highlights: list[Highlight], *, group_prefix: str
) -> list[Highlight]:
    """Mark obvious open/close tag highlights as paired markup."""
    result = list(highlights)
    stacks: defaultdict[str, list[int]] = defaultdict(list)

    for index, highlight in enumerate(tuple(result)):
        tag = _get_markup_tag(highlight)
        if tag is None:
            continue

        tag_name, closing, self_closing = tag
        if self_closing:
            continue
        if closing:
            if not stacks[tag_name]:
                continue
            opening_index = stacks[tag_name].pop()
            group = f"{group_prefix}:{result[opening_index].start}:{highlight.end}"
            if highlight.text.startswith("["):
                forbidden_text = ("[", "]")
            elif highlight.text.endswith("&gt;"):
                forbidden_text = ("&lt;", "&gt;", "<", ">")
            else:
                forbidden_text = ("<", ">")
            result[opening_index] = replace(
                result[opening_index],
                kind="markup",
                group=group,
                translatable=True,
                forbidden_text=forbidden_text,
            )
            result[index] = replace(
                highlight,
                kind="markup",
                group=group,
                translatable=True,
                forbidden_text=forbidden_text,
            )
        else:
            stacks[tag_name].append(index)

    return result


def highlight_pygments(source: str, unit: Unit) -> Generator[Highlight]:
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
                    yield Highlight(start, start + 1, "`", kind="syntax")
                else:
                    yield Highlight(start, start + len(text), text, kind="syntax")
            elif token == Token.Literal.String.Interpol:
                yield Highlight(start, start + len(text), text, kind="syntax")
            elif token == Token.Generic.Strong:
                end = start + len(text)
                group = f"rst-strong:{start}:{end}"
                yield Highlight(start, start + 2, "**", kind="markup", group=group)
                yield Highlight(end - 2, end, "**", kind="markup", group=group)
            elif token == Token.Generic.Emph:
                end = start + len(text)
                group = f"rst-emph:{start}:{end}"
                yield Highlight(start, start + 1, "*", kind="markup", group=group)
                yield Highlight(end - 1, end, "*", kind="markup", group=group)
            start += len(text)


def _highlight_specificity(highlight: Highlight) -> tuple[bool, bool, bool, int]:
    return (
        highlight.group is not None,
        highlight.translatable,
        highlight.role is not None,
        {"grammar": 0, "syntax": 1, "markup": 2}[highlight.kind],
    )


def merge_highlight_spans(source: str, highlights: list[Highlight]) -> list[Highlight]:
    """Merge overlapping highlight spans (nested or partial) into their union intervals."""
    merged: list[Highlight] = []
    for highlight in highlights:
        if merged and highlight.start < merged[-1].end:
            previous = merged[-1]
            if previous.start == highlight.start and previous.end == highlight.end:
                if _highlight_specificity(highlight) > _highlight_specificity(previous):
                    merged[-1] = highlight
                continue
            if previous.start <= highlight.start and previous.end >= highlight.end:
                continue
            new_end = max(previous.end, highlight.end)
            kind = (
                "grammar"
                if previous.kind == "grammar" and highlight.kind == "grammar"
                else "syntax"
            )
            merged[-1] = Highlight(
                previous.start,
                new_end,
                source[previous.start : new_end],
                kind=kind,
            )
        else:
            merged.append(highlight)
    return merged


def highlight_string(
    source: str, unit: Unit, *, highlight_syntax: bool = False
) -> list[Highlight]:
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
    highlights = [highlight for highlight in highlights if highlight.text]

    # Sort by order in string, longest first
    highlights.sort(key=lambda item: (item.start, -item.end))

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
    for highlight in highlights:
        if highlight.start < last_end:
            last_end = max(last_end, highlight.end)
            continue
        result.append(source[last_end : highlight.start])
        if callable(replacement):
            result.append(replacement(highlight.start))
        else:
            result.append(replacement)
        last_end = highlight.end
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
