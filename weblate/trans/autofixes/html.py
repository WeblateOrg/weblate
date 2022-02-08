#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import bleach
from django.utils.translation import gettext_lazy as _

from weblate.checks.markup import MD_LINK
from weblate.trans.autofixes.base import AutoFix
from weblate.utils.html import extract_bleach


class BleachHTML(AutoFix):
    """Cleanup unsafe HTML markup."""

    fix_id = "safe-html"
    name = _("Unsafe HTML")

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

        new_target = bleach.clean(target, **extract_bleach(source))
        for text, replace in replacements.items():
            new_target = new_target.replace(text, replace)
        return new_target, new_target != old_target
