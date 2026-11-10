# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

import regex

if TYPE_CHECKING:
    from collections.abc import Iterator

REGEX_TIMEOUT = 0.3
type RegexMatch = re.Match[str] | regex.Match


@lru_cache(maxsize=128)
def _compile_builtin_regex(pattern: re.Pattern[str]) -> regex.Pattern:
    """Translate standard-library flags to the bounded matching engine."""
    flags = regex.VERSION0
    for name in ("ASCII", "IGNORECASE", "MULTILINE", "DOTALL", "VERBOSE"):
        if pattern.flags & getattr(re, name):
            flags |= getattr(regex, name)
    return regex.compile(pattern.pattern, flags)


def builtin_regex_finditer(
    pattern: re.Pattern[str], value: str
) -> Iterator[regex.Match]:
    """Bound a complete iteration of a built-in pattern, including failed scans."""
    yield from _compile_builtin_regex(pattern).finditer(value, timeout=REGEX_TIMEOUT)


def compile_regex(pattern: str) -> regex.Pattern:
    return regex.compile(pattern)


def regex_match(pattern: str | regex.Pattern, value: str) -> regex.Match | None:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    return compiled.match(value, timeout=REGEX_TIMEOUT)


def regex_findall(pattern: str | regex.Pattern, value: str) -> list[object]:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    return compiled.findall(value, timeout=REGEX_TIMEOUT)


def regex_finditer(
    pattern: str | regex.Pattern, value: str, *, concurrent: bool = False
) -> Iterator[regex.Match]:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    yield from compiled.finditer(value, concurrent=concurrent, timeout=REGEX_TIMEOUT)


def regex_sub(pattern: str | regex.Pattern, replacement: str, value: str) -> str:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    return compiled.sub(replacement, value, timeout=REGEX_TIMEOUT)
