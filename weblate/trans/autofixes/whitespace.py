# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.utils.translation import gettext_lazy

from weblate.checks.chars import BeginSpaceCheck, EndSpaceCheck
from weblate.trans.autofixes.base import AutoFix

NEWLINES = re.compile(r"\r\n|\r|\n")
START = re.compile(r"^(\s+)")
END = re.compile(r"(\s+)$")


class SameBookendingWhitespace(AutoFix):
    """Help non-techy translators with their whitespace."""

    fix_id = "end-whitespace"
    name = gettext_lazy("Trailing and leading whitespace")

    @staticmethod
    def get_related_checks():
        return [BeginSpaceCheck(), EndSpaceCheck()]

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
