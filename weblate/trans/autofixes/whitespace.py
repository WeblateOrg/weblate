#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.utils.translation import gettext_lazy as _

from weblate.trans.autofixes.base import AutoFix

NEWLINES = re.compile(r"\r\n|\r|\n")
START = re.compile(r"^(\s+)", re.UNICODE)
END = re.compile(r"(\s+)$", re.UNICODE)


class SameBookendingWhitespace(AutoFix):
    """Help non-techy translators with their whitespace."""

    fix_id = "end-whitespace"
    name = _("Trailing and leading whitespace")

    def fix_single_target(self, target, source, unit):
        # normalize newlines of source
        source = NEWLINES.sub("\n", source)

        flags = unit.all_flags
        stripped = target

        # Capture and strip leading space
        if "ignore-begin-space" in flags:
            head = ""
        else:
            start = START.search(source)
            head = start.group() if start else ""
            stripped = stripped.lstrip()

        # Capture and strip trailing space
        if "ignore-end-space" in flags:
            tail = ""
        else:
            end = END.search(source)
            tail = end.group() if end else ""
            stripped = stripped.rstrip()

        # add the whitespace around the target translation (ignore blanks)
        if stripped:
            newtarget = head + stripped + tail
            return newtarget, newtarget != target
        return target, False
