# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import re
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _


ALLOWED_IMAGES = frozenset((
    'image/jpeg',
    'image/png',
))

# List of schemes not allowed in editor URL
# This list is not intededed to be complete, just block
# the possibly dangerous ones.
FORBIDDEN_URL_SCHEMES = frozenset((
    'javascript',
    'data',
    'vbscript',
    'mailto',
    'ftp',
    'sms',
    'tel',
))


def validate_re(value):
    try:
        re.compile(value)
    except re.error as error:
        raise ValidationError(_('Failed to compile: {0}').format(error))


def validate_bitmap(value):
    """Validate bitmap, based on django.forms.fields.ImageField"""
    if value is None or not hasattr(value.file, 'content_type'):
        return

    # Check image type
    if value.file.content_type not in ALLOWED_IMAGES:
        raise ValidationError(
            _('Not supported image type: %s') % value.file.content_type
        )

    # Check dimensions
    width, height = value.file.image.size
    if width > 2000 or height > 2000:
        raise ValidationError(
            _('Image is too big, please scale it down or crop relevant part!')
        )


def validate_repoweb(val):
    """Validate whether URL for repository browser is valid.

    It checks whether it can be filled in using format string.
    """
    try:
        val % {'file': 'file.po', 'line': '9', 'branch': 'master'}
    except Exception as error:
        raise ValidationError(_('Bad format string (%s)') % str(error))


def validate_editor(val):
    """Validate URL for custom editor link.

    - Check whether it correctly uses format strings.
    - Check whether scheme is sane.
    """
    if not val:
        return
    validate_repoweb(val)

    if ':' not in val:
        raise ValidationError(_('The editor link lacks URL scheme!'))

    scheme = val.split(':', 1)[0]

    if scheme.strip().lower() in FORBIDDEN_URL_SCHEMES:
        raise ValidationError(_('Forbidden URL scheme!'))


def clean_fullname(val):
    """Remove special chars from user full name."""
    if not val:
        return val
    val = val.strip()
    for i in range(0x20):
        val = val.replace(chr(i), '')
    return val
