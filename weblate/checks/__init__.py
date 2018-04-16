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
from weblate.utils.classloader import ClassLoader

default_app_config = 'weblate.checks.apps.ChecksConfig'


def highlight_string(source, unit):
    """Return highlights for a string"""
    if unit is None:
        return []
    highlights = []
    for check in CHECKS:
        if not CHECKS[check].target:
            continue
        highlights += CHECKS[check].check_highlight(source, unit)

    # Sort by order in string
    highlights.sort(key=lambda x: x[0])

    # Remove overlapping ones
    for hl_idx in range(0, len(highlights)):
        if hl_idx >= len(highlights):
            break
        elref = highlights[hl_idx]
        for hl_idx_next in range(hl_idx + 1, len(highlights)):
            if hl_idx_next >= len(highlights):
                break
            eltest = highlights[hl_idx_next]
            if eltest[0] >= elref[0] and eltest[0] < elref[1]:
                highlights.pop(hl_idx_next)
            elif eltest[0] > elref[1]:
                break

    return highlights


# Initialize checks list
CHECKS = ClassLoader('CHECK_LIST')
