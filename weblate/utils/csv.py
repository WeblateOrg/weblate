# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The following characters are considered problematic for CSV files
# - due to how they are interpreted by Excel
# - due to the risk of CSV injection attacks

from __future__ import annotations

from weblate.utils.unicodechars import WHITESPACE_CHARS

CSV_FORMULA_TRIGGERS: set[str] = {"=", "+", "-", "@", "|", "%"}

PROHIBITED_INITIAL_CHARS: set[str] = CSV_FORMULA_TRIGGERS | WHITESPACE_CHARS


def escape_csv_formula(text: str) -> str:
    """Prevent spreadsheet applications from interpreting a CSV cell as a formula."""
    if text and text[0] in PROHIBITED_INITIAL_CHARS:
        return "'{}'".format(text.replace("|", "\\|"))
    return text


# Escape the whitespaces so they are rendered as their string representation instead of an actual character
# This is later passed to format_html_join_comma
PROHIBITED_INITIAL_CHARS_FOR_DISPLAY: tuple[tuple[str], ...] = tuple(
    (char if char in CSV_FORMULA_TRIGGERS else f"\\u{ord(char):04x}",)
    for char in PROHIBITED_INITIAL_CHARS
)
