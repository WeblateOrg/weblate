# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from diff_match_patch import diff_match_patch
from django.utils.html import format_html


class Differ:
    def __init__(self):
        self.dmp = diff_match_patch()

    def highlight(self, new, old):
        dmp = self.dmp
        diff = dmp.diff_main(old, new)
        dmp.diff_cleanupSemantic(diff)
        output = []
        for op, data in diff:
            if op == dmp.DIFF_DELETE:
                template = "<del>{}</del>"
            elif op == dmp.DIFF_INSERT:
                template = "<ins>{}</ins>"
            elif op == dmp.DIFF_EQUAL:
                template = "{}"
            output.append(format_html(template, data))
        return "".join(output)
