# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


MESSAGE_PREFIX = re.compile(r"{\d+\s*(,\s*[a-z]+(?P<style>,\s*)?)?\s*")
AUTO_MESSAGE_PREFIX = re.compile(r"{\s*\d+\s*(,\s*[a-z]+(?P<style>,\s*)?)?\s*")


def iter_java_message_matches(
    text: str, regexp: re.Pattern[str], *, leading_space: bool = False
) -> Iterator[re.Match[str]]:
    """Match MessageFormat strings without rescanning failed style suffixes."""
    if "{" not in text or "}" not in text:
        return
    # A style can end at the last brace in its non-whitespace run, or at a
    # brace immediately after trailing whitespace. Cache that choice once.
    closers = [-1] * len(text)
    closer = next_nonspace = -1
    for position in range(len(text) - 1, -1, -1):
        char = text[position]
        if char.isspace():
            closer = (
                next_nonspace
                if next_nonspace != -1 and text[next_nonspace] == "}"
                else -1
            )
        else:
            next_nonspace = position
            if char == "}" and closer == -1:
                closer = position
            if closer > position:
                closers[position] = closer

    prefix = AUTO_MESSAGE_PREFIX if leading_space else MESSAGE_PREFIX
    consumed = 0
    for opener in re.finditer(r"{", text):
        start = opener.start()
        if start < consumed:
            continue
        head = prefix.match(text, start)
        if head is None or head.end() == len(text):
            continue
        if head.group("style") is not None:
            closing = closers[head.end()]
            if closing == -1:
                continue
        elif text[head.end()] == "}":
            closing = head.end()
        else:
            continue
        match = regexp.match(text, start, closing + 1)
        if match is not None:
            yield match
            consumed = match.end()
