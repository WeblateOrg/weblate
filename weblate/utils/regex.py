# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import regex

REGEX_TIMEOUT = 0.2


def compile_regex(pattern: str) -> regex.Pattern:
    return regex.compile(pattern)


def regex_match(pattern: str | regex.Pattern, value: str) -> regex.Match | None:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    return compiled.match(value, timeout=REGEX_TIMEOUT)


def regex_findall(pattern: str | regex.Pattern, value: str) -> list[object]:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    return compiled.findall(value, timeout=REGEX_TIMEOUT)


def regex_sub(pattern: str | regex.Pattern, replacement: str, value: str) -> str:
    compiled = compile_regex(pattern) if isinstance(pattern, str) else pattern
    return compiled.sub(replacement, value, timeout=REGEX_TIMEOUT)
