# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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

import hashlib

PLURAL_SEPARATOR = '\x00\x00'

def is_plural(s):
    '''
    Checks whether string is plural form.
    '''
    return s.find(PLURAL_SEPARATOR) != -1

def split_plural(s):
    return s.split(PLURAL_SEPARATOR)

def join_plural(s):
    return PLURAL_SEPARATOR.join(s)

def msg_checksum(source, context):
    '''
    Returns checksum of source string, used for quick lookup.

    We use MD5 as it is faster than SHA1.
    '''
    m = hashlib.md5()
    m.update(source.encode('utf-8'))
    m.update(context.encode('utf-8'))
    return m.hexdigest()

def is_unit_key_value(unit):
    '''
    Checks whether unit is key = value based rather than
    translation.

    These are some files like PHP or properties, which for some
    reason do not correctly set source/target attributes.
    '''
    return (
        hasattr(unit, 'name')
        and hasattr(unit, 'value')
        and hasattr(unit, 'translation')
    )

def get_source(unit):
    '''
    Returns source string from a ttkit unit.
    '''
    if is_unit_key_value(unit):
        return unit.name
    else:
        if hasattr(unit.source, 'strings'):
            return join_plural(unit.source.strings)
        else:
            return unit.source

def get_target(unit):
    '''
    Returns target string from a ttkit unit.
    '''
    if unit is None:
        return ''
    if is_unit_key_value(unit):
        return unit.value
    else:
        if hasattr(unit.target, 'strings'):
            return join_plural(unit.target.strings)
        else:
            return unit.target


