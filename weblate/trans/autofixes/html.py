# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import nh3
from django.utils.translation import gettext_lazy

from weblate.checks.markup import MD_LINK
from weblate.trans.autofixes.base import AutoFix
from weblate.utils.html import extract_html_tags


class BleachHTML(AutoFix):
    """Cleanup unsafe HTML markup."""

    fix_id = "safe-html"
    name = gettext_lazy("Unsafe HTML")

    def fix_single_target(self, target, source, unit):
        flags = unit.all_flags
        if "safe-html" not in flags:
            return target, False

        old_target = target

        # Strip MarkDown links
        replacements = {}
        current = 0

        def handle_replace(match):
            nonlocal current, replacements
            current += 1
            replacement = f"@@@@@weblate:{current}@@@@@"
            replacements[replacement] = match.group(0)
            return replacement

        if "md-text" in flags:
            target = MD_LINK.sub(handle_replace, target)

        new_target = nh3.clean(target, link_rel=None, **extract_html_tags(source))
        for text, replace in replacements.items():
            new_target = new_target.replace(text, replace)
        return new_target, new_target != old_target
