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

from trans.autofixes.base import AutoFix


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    '''
    Replace Trailing Dots with an Ellipsis.
    '''
    def fix_single_target(self, target, source, unit):
        if (source[-1] == u'…' and target.endswith('...')):
            target = u'%s…' % target[:-3]
        return target


class RemoveZeroSpace(AutoFix):
    '''
    Remove zero width space if there is none in the source.
    '''
    def fix_single_target(self, target, source, unit):
        if u'\u200b' not in source and u'\u200b' in target:
            return target.replace(u'\u200b', '')
        return target
