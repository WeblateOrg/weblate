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
"""Import all the autofixes defined in settings.

Note, unlike checks, using a sortable data object so fixes are applied in
desired order.
"""

from weblate.utils.classloader import ClassLoader

AUTOFIXES = ClassLoader('AUTOFIX_LIST')


def fix_target(target, unit):
    """Apply each autofix to the target translation."""
    if target == []:
        return target, []
    fixups = []
    for dummy, fix in AUTOFIXES.items():
        target, fixed = fix.fix_target(target, unit)
        if fixed:
            fixups.append(fix.name)

    return target, fixups
