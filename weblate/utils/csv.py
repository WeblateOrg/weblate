# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The following characters are considered problematic for CSV files
# - due to how they are interpreted by Excel
# - due to the risk of CSV injection attacks

from weblate.utils.unicodechars import WHITESPACE_CHARS

CSV_FORMULA_TRIGGERS: set[str] = {"=", "+", "-", "@", "|", "%"}

PROHIBITED_INITIAL_CHARS: set[str] = CSV_FORMULA_TRIGGERS | WHITESPACE_CHARS

# Escape the whitespaces so they are rendered as their string representation instead of an actual character
# This is later passed to format_html_join_comma
PROHIBITED_INITIAL_CHARS_FOR_DISPLAY: tuple[tuple[str], ...] = tuple(
    (char if char in CSV_FORMULA_TRIGGERS else f"\\u{ord(char):04x}",)
    for char in PROHIBITED_INITIAL_CHARS
)
