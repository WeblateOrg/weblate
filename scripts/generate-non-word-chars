#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Generates list of non-word chars.

Used in weblate/checks/data.py
"""

import pprint
import sys
import unicodedata

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
print("NON_WORD_CHARS = ")
pprint.pprint(
    [
        char
        for char in map(chr, range(sys.maxunicode + 1))
        if char not in EXCLUDES and unicodedata.category(char) in CATEGORIES
    ]
)
print("COMPOSITING_CHARS = {")
for char in map(chr, range(sys.maxunicode + 1)):
    if unicodedata.category(char) == "Mn":
        print('    "{}",'.format(char.encode("unicode-escape").decode()))
print("}")
