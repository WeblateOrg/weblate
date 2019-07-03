# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

ESCAPED = frozenset(".\\+*?[^]$(){}=!<>|:-")


def re_escape(pattern):
    """Escape for use in database regexp match.

    This is based on re.escape, but that one escapes too much.
    """
    string = list(pattern)
    for i, char in enumerate(pattern):
        if char == "\000":
            string[i] = "\\000"
        elif char in ESCAPED:
            string[i] = "\\" + char
    return "".join(string)


def table_has_row(connection, table, rowname):
    """Check whether actual table has row."""
    with connection.cursor() as cursor:
        table_description = connection.introspection.get_table_description(
            cursor, table
        )
        for row in table_description:
            if row.name == rowname:
                return True
    return False
