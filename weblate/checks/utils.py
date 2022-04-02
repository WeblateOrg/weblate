# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from pygments.lexers.markup import RstLexer
from pygments.token import Token

from weblate.checks.models import CHECKS


def highlight_pygments(source: str, unit):
    """
    Highlight syntax characters using pygments.

    This is not really a full syntax highlighting, we're only interested in
    non-translatable strings.
    """
    if "rst-text" in unit.all_flags:
        lexer = RstLexer(stripnl=False)
        start = 0
        for token, text in lexer.get_tokens(source):
            if token == Token.Literal.String:
                if text[0] == "`" and text != "`_":
                    yield ((start, start + 1, "`"))
                else:
                    yield ((start, start + len(text), text))
            elif token == Token.Literal.String.Interpol:
                yield ((start, start + len(text), text))
            elif token == Token.Generic.Strong:
                end = start + len(text)
                yield (start, start + 2, "**")
                yield (end - 2, end, "**")
            elif token == Token.Generic.Emph:
                end = start + len(text)
                yield (start, start + 1, "*")
                yield (end - 1, end, "*")
            start += len(text)


def highlight_string(source: str, unit, hightlight_syntax: bool = False):
    """Return highlights for a string."""
    if unit is None:
        return []
    highlights = []
    for check in CHECKS:
        if not CHECKS[check].target:
            continue
        highlights.extend(CHECKS[check].check_highlight(source, unit))

    if hightlight_syntax:
        highlights.extend(highlight_pygments(source, unit))

    # Remove empty strings
    highlights = [highlight for highlight in highlights if highlight[2]]

    # Sort by order in string
    highlights.sort(key=lambda x: x[0])

    # Remove overlapping ones
    for hl_idx in range(0, len(highlights)):
        if hl_idx >= len(highlights):
            break
        elref = highlights[hl_idx]
        for hl_idx_next in range(hl_idx + 1, len(highlights)):
            if hl_idx_next >= len(highlights):
                break
            eltest = highlights[hl_idx_next]
            if eltest[0] >= elref[0] and eltest[0] < elref[1]:
                # Elements overlap, remove inner one
                highlights.pop(hl_idx_next)
            elif eltest[0] > elref[1]:
                # This is not an overlapping element
                break

    return highlights
