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
"""
This is reimplementation of
https://github.com/freeplane/freeplane/blob/1.4.x/freeplane_ant/
src/main/java/org/freeplane/ant/FormatTranslation.java
"""

from __future__ import unicode_literals

import re

from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_PRE_COMMIT

SPLITTER = re.compile(r'\s*=\s*')
UNICODE = re.compile(r'\\[uU][0-9a-fA-F]{4}')


def sort_key(line):
    """Sort key for properties."""
    prefix = SPLITTER.split(line, 1)[0]
    return prefix.lower()


def unicode_format(match):
    """Callback for re.sub for formatting unicode chars."""
    return '\\u{0}'.format(match.group(0)[2:].upper())


def fix_newlines(lines):
    """Convert newlines to unix."""
    for i, line in enumerate(lines):
        if line.endswith('\r\n'):
            lines[i] = line[:-2] + '\n'
        elif line.endswith('\r'):
            lines[i] = line[:-1] + '\n'


def format_unicode(lines):
    """Standard formatting for unicode chars."""
    for i, line in enumerate(lines):
        if UNICODE.findall(line) is None:
            continue
        lines[i] = UNICODE.sub(unicode_format, line)


def value_quality(value):
    """Calculate value quality."""
    if not value:
        return 0
    if '[translate me]' in value:
        return 1
    if '[auto]' in value:
        return 2
    return 3


def filter_lines(lines):
    """Filter comments, empty lines and duplicate strings."""
    result = []
    lastkey = None
    lastvalue = None

    for line in lines:
        # Skip comments and blank lines
        if line[0] == '#' or line.strip() == '':
            continue
        parts = SPLITTER.split(line, 1)

        # Missing = or empty key
        if len(parts) != 2 or not parts[0]:
            continue

        key, value = parts
        # Strip trailing \n in value
        value = value[:-1]

        # Empty translation
        if value in ('', '[auto]', '[translate me]'):
            continue

        # Check for duplicate key
        if key == lastkey:
            # Skip duplicate
            if value == lastvalue:
                continue

            quality = value_quality(value)
            lastquality = value_quality(lastvalue)

            if quality > lastquality:
                # Replace lower quality with new one
                result.pop()
            elif lastquality > quality or quality < 4:
                # Drop lower quality one
                continue

        result.append(line)
        lastkey = key
        lastvalue = value

    return result


def format_file(filename):
    """Format single properties file."""
    with open(filename, 'r') as handle:
        lines = handle.readlines()

    result = sorted(lines, key=sort_key)

    fix_newlines(result)
    format_unicode(result)
    result = filter_lines(result)

    if lines != result:
        with open(filename, 'w') as handle:
            handle.writelines(result)


class PropertiesSortAddon(BaseAddon):
    events = (EVENT_PRE_COMMIT,)
    name = 'weblate.properties.sort'
    verbose = _('Formats the Java properties file')
    description = _(
        'This addon sorts the Java properties file.'
    )
    compat = {
        'file_format': frozenset(('properties-utf8', 'properties')),
    }
    icon = 'sort-alpha-asc'

    def pre_commit(self, translation, author):
        format_file(translation.get_filename())
