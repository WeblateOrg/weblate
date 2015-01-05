# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import re
from django.utils.translation import ugettext_lazy as _
from weblate.trans.autofixes.base import AutoFix


class SameBookendingWhitespace(AutoFix):
    '''
    Help non-techy translators with their whitespace
    '''

    name = _('Trailing and leading whitespace')

    def fix_single_target(self, target, source, unit):
        # normalize newlines of source
        source = re.compile(r'\r\n|\r|\n').sub('\n', source)

        # capture preceding and tailing whitespace
        start = re.compile(r'^(\s+)').search(source)
        end = re.compile(r'(\s+)$').search(source)
        head = start.group() if start else ''
        tail = end.group() if end else ''

        # add the whitespace around the target translation (ignore blanks)
        stripped = target.strip()
        if stripped:
            newtarget = '%s%s%s' % (head, stripped, tail)
            return newtarget, newtarget != target
        return target, False
