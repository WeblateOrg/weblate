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

from __future__ import unicode_literals

from django.utils.translation import ugettext_lazy as _

from weblate.trans.autofixes.base import AutoFix


CONTROLCHARS = frozenset((
    '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', '\x08',
    '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13', '\x14',
    '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d',
    '\x1e', '\x1f'
))


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    """Replace Trailing Dots with an Ellipsis."""

    fix_id = 'end-ellipsis'
    name = _('Trailing ellipsis')

    def fix_single_target(self, target, source, unit):
        if source and source[-1] == '…' and target.endswith('...'):
            return '{0}…'.format(target[:-3]), True
        return target, False


class RemoveZeroSpace(AutoFix):
    """Remove zero width space if there is none in the source."""

    fix_id = 'zero-width-space'
    name = _('Zero-width space')

    def fix_single_target(self, target, source, unit):
        if unit.translation.language.code.split('_')[0] == 'km':
            return target, False
        if '\u200b' not in source and '\u200b' in target:
            return target.replace('\u200b', ''), True
        return target, False


class RemoveControlChars(AutoFix):
    """Remove control chars from the string."""

    fix_id = 'control-chars'
    name = _('Control chars')

    def fix_single_target(self, target, source, unit):
        modified = False
        for char in CONTROLCHARS:
            if char not in source and char in target:
                target = target.replace(char, '')
                modified = True
        return target, modified
