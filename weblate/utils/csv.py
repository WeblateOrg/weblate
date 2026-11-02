# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The following characters are considered problematic for CSV files
# - due to how they are interpreted by Excel
# - due to the risk of CSV injection attacks

from __future__ import annotations

import unicodedata

from weblate.utils.unicodechars import WHITESPACE_CHARS

CSV_FORMULA_TRIGGERS: set[str] = {"=", "+", "-", "@", "|", "%"}
CSV_IGNORABLE_CATEGORIES = frozenset(
    {"Cc", "Cf", "Cn", "Cs", "Zs", "Zl", "Zp", "Mn", "Mc", "Me"}
)
# These visually blank characters are letters or symbols, not spacing or marks.
CSV_IGNORABLE_CHARACTERS = frozenset("\u115f\u1160\u3164\uffa0\u2800")

PROHIBITED_INITIAL_CHARS: set[str] = CSV_FORMULA_TRIGGERS | WHITESPACE_CHARS


def csv_starts_with_formula(text: str) -> bool:
    """Detect formula signs behind leading invisible or spacing characters."""
    for char in text:
        if (
            unicodedata.category(char) in CSV_IGNORABLE_CATEGORIES
            or char in CSV_IGNORABLE_CHARACTERS
        ):
            continue
        return unicodedata.normalize("NFKC", char) in CSV_FORMULA_TRIGGERS
    return False


def escape_csv_formula(text: str) -> str:
    """Prevent spreadsheet applications from interpreting a CSV cell as a formula."""
    if text and (text[0] in PROHIBITED_INITIAL_CHARS or csv_starts_with_formula(text)):
        return "'{}'".format(text.replace("|", "\\|"))
    return text


# Escape the whitespaces so they are rendered as their string representation instead of an actual character
# This is later passed to format_html_join_comma
PROHIBITED_INITIAL_CHARS_FOR_DISPLAY: tuple[tuple[str], ...] = tuple(
    (char if char in CSV_FORMULA_TRIGGERS else f"\\u{ord(char):04x}",)
    for char in PROHIBITED_INITIAL_CHARS
)
