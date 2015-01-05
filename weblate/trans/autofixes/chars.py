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

from weblate.trans.autofixes.base import AutoFix
from django.utils.translation import ugettext_lazy as _


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    '''
    Replace Trailing Dots with an Ellipsis.
    '''

    name = _('Trailing ellipsis')

    def fix_single_target(self, target, source, unit):
        if source and source[-1] == u'…' and target.endswith('...'):
            return u'%s…' % target[:-3], True
        return target, False


class RemoveZeroSpace(AutoFix):
    '''
    Remove zero width space if there is none in the source.
    '''

    name = _('Zero-width space')

    def fix_single_target(self, target, source, unit):
        if unit.translation.language.code.split('_')[0] == 'km':
            return target, False
        if u'\u200b' not in source and u'\u200b' in target:
            return target.replace(u'\u200b', ''), True
        return target, False
