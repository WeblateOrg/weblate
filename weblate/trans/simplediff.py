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

from difflib import SequenceMatcher


def html_diff(old, new):
    '''
    Generates HTML formatted diff of two strings.
    '''
    diff = SequenceMatcher(None, old, new)
    result = []
    for tag, oldpos1, oldpos2, newpos1, newpos2 in diff.get_opcodes():
        if tag == 'replace':
            result.append(
                '<del>%s</del><ins>%s</ins>' %
                (old[oldpos1:oldpos2], new[newpos1:newpos2])
            )
        elif tag == 'delete':
            result.append(
                '<del>%s</del>' % old[oldpos1:oldpos2]
            )
        elif tag == 'insert':
            result.append(
                '<ins>%s</ins>' % new[newpos1:newpos2]
            )
        elif tag == 'equal':
            result.append(new[newpos1:newpos2])
    return ''.join(result)
