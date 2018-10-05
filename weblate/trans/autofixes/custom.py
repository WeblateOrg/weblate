# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
"""
Auto fixes implemeted for specific environments and not enabled by default.
"""

from __future__ import unicode_literals

import re

from django.utils.translation import ugettext_lazy as _

from weblate.trans.autofixes.base import AutoFix

QUOTE_PARAM = re.compile(r"'(\{[^}]+\})'")
SINGLE_APO = re.compile(r"'{1,3}")
DOUBLE_APO = re.compile(r"'{4,}")
REPLACEMENT = '__weblate:quote__'
REPLACE_STRING = r'{0}\1{0}'.format(REPLACEMENT)


class DoubleApostrophes(AutoFix):
    """Ensures apostrophes are escaped in Java Properties MessageFormat string

    - all apostrophes except ones around {} vars are doubled

    Note: This fix is not really generically applicable in all cases, that's
    why it's not enabled by default.
    """

    fix_id = 'java-messageformat'
    name = _('Apostrophes in Java MessageFormat')

    def fix_single_target(self, target, source, unit):
        flags = unit.all_flags
        if (('auto-java-messageformat' not in flags or '{0' not in source) and
                ('java-messageformat' not in flags)):
            return target, False
        # Split on apostrophe
        new = SINGLE_APO.sub("''", DOUBLE_APO.sub(
            "''''", QUOTE_PARAM.sub(REPLACE_STRING, target)
        )).replace(REPLACEMENT, "'")
        return new, new != target
