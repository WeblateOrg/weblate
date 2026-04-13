# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

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
    from pygments.lexers.markup import RstLexer  # noqa: PLC0415
    from pygments.token import Token  # noqa: PLC0415

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

    # Remove overlapping ones
    # pylint: disable-next=consider-using-enumerate
    for hl_idx in range(len(highlights)):
        if hl_idx >= len(highlights):
            break
        elref = highlights[hl_idx]
        hl_idx_next = hl_idx + 1
        while hl_idx_next < len(highlights):
            eltest = highlights[hl_idx_next]
            if eltest[0] >= elref[0] and eltest[1] <= elref[1]:
                # Elements overlap, remove inner one
                highlights.pop(hl_idx_next)
                # Do not increment index here as we've removed the current element
            elif eltest[0] > elref[1]:
                # This is not an overlapping element
                break
            else:
                # Increase index to test
                hl_idx_next += 1

    return highlights


def replace_highlighted(
    source: str,
    unit: Unit,
    replacement: str | Callable[[int], str] = "",
    *,
    highlight_syntax: bool = False,
) -> str:
    """Replace highlighted ranges in source string."""
    highlights = highlight_string(source, unit, highlight_syntax=highlight_syntax)
    if not highlights:
        return source

    result = []
    last_end = 0
    for start, end, _text in highlights:
        if start < last_end:
            continue
        result.append(source[last_end:start])
        if callable(replacement):
            result.append(replacement(start))
        else:
            result.append(replacement)
        last_end = end
    result.append(source[last_end:])
    return "".join(result)


def placeholder_replacement(start_index: int) -> str:
    return f"x-weblate-{start_index}"
