#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Generates list of non-word chars.

Used in weblate/utils/unicodechars.py
"""

import sys
import unicodedata


def filter_chars(categories: set[str]) -> list[str]:
    return [
        char
        for char in map(chr, range(sys.maxunicode + 1))
        if unicodedata.category(char) in categories
    ]


def print_chars(data: list[str]) -> None:
    for char in data:
        if char == '"':
            value = """'"'"""
        else:
            value = '"{}"'.format(char.encode("unicode-escape").decode())
        print(f"    {value},")


print("""# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# This file is generated using ./scripts/generate-unicodechars.py
""")

# Unicode categories to consider non word chars
CATEGORIES = {"Po", "Ps", "Zs", "Cc", "Sk"}
# Excluded chars
EXCLUDES = {
    # Removed to avoid breaking regexp syntax
    "]",
    # We intentionally skip following
    "-",
    # Allow same words at sentence boundary
    ";",
    ":",
    ",",
    ".",
    # Used in Catalan ŀ
    "·",
    "•",
}

print()
print("# Set of non word characters")
print("NON_WORD_CHARS: tuple[str, ...] = (")
print_chars(
    [
        char
        for char in map(chr, range(sys.maxunicode + 1))
        if char not in EXCLUDES and unicodedata.category(char) in CATEGORIES
    ]
)
print(")")

print()
print("# Compositing characters that should not be split in a diff")
print("COMPOSITING_CHARS: set[str] = {")
print_chars(filter_chars({"Mn"}))
print("}")

print()
print("# Whitespace characters")
print("WHITESPACE_CHARS: set[str] = {")
print_chars(filter_chars({"Zs"}))
print("}")

print()
print("# All control chars including tab and newline, this is different from")
print("# weblate.formats.helpers.CONTROLCHARS which contains only chars")
print("# problematic in XML or SQL scopes.")
print("CONTROLCHARS: tuple[str, ...] = (")
print_chars(filter_chars({"Zl", "Cc"}))
print(")")
