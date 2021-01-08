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

from weblate.checks.format import BaseFormatCheck

QT_FORMAT_MATCH = re.compile(
    r"""
    %(                     # initial %
          L?               # optional localized representation of numbers
          (?P<ord>\d{1,2}) # variable order, like %1
    )""",
    re.VERBOSE,
)

QT_PLURAL_MATCH = re.compile(
    r"""
    %(                     # initial %
          L?               # optional localized representation of numbers
          (?P<type>n)      # plural: %n
    )""",
    re.VERBOSE,
)


class QtFormatCheck(BaseFormatCheck):
    """Check for Qt format string."""

    check_id = "qt_format"
    name = _("Qt format")
    description = _("Qt format string does not match source")
    regexp = QT_FORMAT_MATCH

    def is_position_based(self, string):
        # everything is numbered
        return False


class QtPluralCheck(BaseFormatCheck):
    """Check for Qt plural string."""

    check_id = "qt_plural_format"
    name = _("Qt plural format")
    description = _("Qt plural format string does not match source")
    regexp = QT_PLURAL_MATCH

    def is_position_based(self, string):
        return True
