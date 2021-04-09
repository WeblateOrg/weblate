#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import re
import sys
import unicodedata

from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck

# Unicode categories to consider non word chars
CATEGORIES = {"Po", "Zs"}
# Excluded chars
EXCLUDES = {
    # Removed to avoid breaking regexp syntax
    "]",
    # We intentionally skip following
    "-",
    # Used in Catalan ŀ
    "·",
    "•",
}
# Set of non word characters
NON_WORD_CHARS = {
    char
    for char in map(chr, range(sys.maxunicode + 1))
    if char not in EXCLUDES and unicodedata.category(char) in CATEGORIES
}
# Regexp for non word chars
NON_WORD = "[{}\\]]".format("".join(NON_WORD_CHARS))
# Look for non-digit word sequences
CHECK_RE = re.compile(
    rf"""
    (?:{NON_WORD}|^)    # Word boundary
    ([^\d\W]{{2,}})       # Word to match
    (?:{NON_WORD}+\1)   # Space + repeated word
    (?={NON_WORD}|$)    # Word boundary
    """,
    re.VERBOSE,
)

# Per language ignore list
IGNORES = {
    "fr": {"vous", "nous"},
    "hi": {"कर"},
    "tr": {"tek"},
}


class DuplicateCheck(TargetCheck):
    """Check for duplicated tokens."""

    check_id = "duplicate"
    name = _("Consecutive duplicated words")
    description = _("Text contains the same word twice in a row:")

    def check_single(self, source, target, unit):
        lang_code = unit.translation.language.base_code
        source_matches = set(CHECK_RE.findall(source))
        target_matches = set(CHECK_RE.findall(target))
        diff = target_matches - source_matches
        if lang_code in IGNORES:
            diff = diff - IGNORES[lang_code]
        return bool(diff)

    def get_description(self, check_obj):
        duplicate = set()
        for target in check_obj.unit.get_target_plurals():
            duplicate.update(CHECK_RE.findall(target))
        return mark_safe(
            "{} {}".format(
                escape(self.description), escape(", ".join(sorted(duplicate)))
            )
        )
