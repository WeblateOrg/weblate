# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from diff_match_patch import diff_match_patch
from django.utils.html import format_html


class Differ:
    DIFF_DELETE = diff_match_patch.DIFF_DELETE
    DIFF_INSERT = diff_match_patch.DIFF_INSERT
    DIFF_EQUAL = diff_match_patch.DIFF_EQUAL

    def __init__(self):
        self.dmp = diff_match_patch()

    def compare(self, new: str, old: str) -> list[tuple(str, str)]:
        dmp = self.dmp
        diff = dmp.diff_main(old, new)
        dmp.diff_cleanupSemantic(diff)
        dmp.diff_cleanupEfficiency(diff)
        return diff

    def highlight(self, new: str, old: str) -> str:
        diff = self.compare(new, old)
        output = []
        for op, data in diff:
            if op == self.DIFF_DELETE:
                template = "<del>{}</del>"
            elif op == self.DIFF_INSERT:
                template = "<ins>{}</ins>"
            elif op == self.DIFF_EQUAL:
                template = "{}"
            output.append(format_html(template, data))
        return "".join(output)
