# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from base import AutoFix


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    '''
    Replace Trailing Dots with an Ellipsis.
    Ignore and maintain exisiting trailing whitespace
    '''
    def fix_single_target(self, target, unit):
        source_match = re.compile(u'…(\s*)$').search(unit.get_source_plurals()[0])
        re_dots = re.compile(u'\.\.\.(\s*)$')
        target_match = re_dots.search(target)
        if source_match and target_match:
            elip_whitespace = u'…' + target_match.group(1)
            target = re_dots.sub(elip_whitespace, target)
        return target
