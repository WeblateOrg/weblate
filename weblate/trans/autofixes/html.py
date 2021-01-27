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


import bleach
from django.utils.translation import gettext_lazy as _

from weblate.trans.autofixes.base import AutoFix
from weblate.utils.html import extract_bleach


class BleachHTML(AutoFix):
    """Cleanup unsafe HTML markup."""

    fix_id = "safe-html"
    name = _("Unsafe HTML")

    def fix_single_target(self, target, source, unit):
        if "safe-html" not in unit.all_flags:
            return target, False

        newtarget = bleach.clean(target, **extract_bleach(source))
        return newtarget, newtarget != target
