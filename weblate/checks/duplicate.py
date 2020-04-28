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

from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck


class DuplicateCheck(TargetCheck):
    """Check for duplicated tokens."""

    check_id = "duplicate"
    name = _("Consecutive duplicated tokens")
    description = _("Text contains the same token twice in a row")
    severity = "warning"

    def check_single(self, source, target, unit):
        if re.search(r"\b(\w+)(?:\s+\1)+\b", target):
            return True
        return False
