# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
"""
Helper code to get user special chars specific for given language.
"""

from django.utils.translation import ugettext as _


SPECIAL_CHARS = (u'→', u'↵', u'…')
CHAR_NAMES = {
    u'→': _('Insert tab character'),
    u'↵': _('Insert new line'),
    u'…': _('Insert horizontal ellipsis'),
}


def get_special_chars():
    """
    Returns list of special characters.
    """
    for char in SPECIAL_CHARS:
        if char in CHAR_NAMES:
            name = CHAR_NAMES[char]
        else:
            name = _('Insert character {0}').format(char)
        yield name, char
