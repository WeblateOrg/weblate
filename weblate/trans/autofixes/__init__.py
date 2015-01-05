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
'''
Import all the autofixes defined in settings.  Note, unlike checks, using
a sortable data object so fixes are applied in desired order.
'''

from weblate import appsettings
from weblate.trans.util import load_class

autofixes = []
for path in appsettings.AUTOFIX_LIST:
    autofixes.append(load_class(path)())


def fix_target(target, unit):
    '''
    Apply each autofix to the target translation.
    '''
    fixups = []
    for fix in autofixes:
        target, fixed = fix.fix_target(target, unit)
        if fixed:
            fixups.append(fix.name)

    return target, fixups
