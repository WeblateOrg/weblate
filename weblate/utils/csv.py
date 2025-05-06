# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# The following characters are considered problematic for CSV files
# - due to how they are interpreted by Excel
# - due to the risk of CSV injection attacks
import sys
import unicodedata

csv_formula_triggers = {"=", "+", "-", "@", "|", "%"}
unicode_whitespaces = {
    chr(c) for c in range(sys.maxunicode + 1) if unicodedata.category(chr(c)) == "Zs"
}

PROHIBITED_INITIAL_CHARS = csv_formula_triggers | unicode_whitespaces

# escape the whitespaces so they are rendered as their string representation instead of an actual character
PROHIBITED_INITIAL_CHARS_FOR_DISPLAY = csv_formula_triggers | {
    (f"\\u{ord(char):04x}",) for char in unicode_whitespaces
}
