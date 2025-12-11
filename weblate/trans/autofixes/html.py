# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy

from weblate.checks.markup import SafeHTMLCheck
from weblate.trans.autofixes.base import AutoFix
from weblate.utils.html import HTMLSanitizer


class BleachHTML(AutoFix):
    """Cleanup unsafe HTML markup."""

    fix_id = "safe-html"
    name = gettext_lazy("Unsafe HTML")

    @staticmethod
    def get_related_checks():
        return [SafeHTMLCheck()]

    def fix_single_target(self, target: str, source: str, unit):
        flags = unit.all_flags
        if "safe-html" not in flags or "ignore-safe-html" in flags:
            return target, False

        sanitizer = HTMLSanitizer()
        new_target = sanitizer.clean(target, source, flags)

        return new_target, new_target != target
