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

from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck

# Look for non-digit word sequences
CHECK_RE = re.compile(r"\b([^\d\W]{2,})(?:\s+\1)\b")

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
        source_matches = set(CHECK_RE.findall(source))
        target_matches = set(CHECK_RE.findall(target))
        diff = target_matches - source_matches
        if unit.translation.language.base_code in IGNORES:
            diff = diff - IGNORES[unit.translation.language.base_code]
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
