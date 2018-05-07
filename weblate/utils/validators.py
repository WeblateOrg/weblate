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

from io import BytesIO
import os
import re
import sys

from PIL import Image

import six

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email as validate_email_django
from django.utils.translation import ugettext as _

from weblate.utils.render import render_template


USERNAME_MATCHER = re.compile(r'^[\w@+-][\w.@+-]*$')

# Reject some suspicious email addresses, based on checks enforced by Exim MTA
EMAIL_BLACKLIST = re.compile(r'^([./|]|.*([@%!`#&?]|/\.\./))')

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

# File formats we do not accept on translation/glossary upload
FORBIDDEN_EXTENSIONS = frozenset((
    '.png',
    '.jpg',
    '.gif',
    '.svg',
    '.doc',
    '.rtf',
    '.xls',
    '.docx',
    '.xlsx',
    '.html',
    '.py',
    '.js',
    '.exe',
    '.dll',
    '.zip',
))


def validate_re(value, groups=None):
    try:
        compiled = re.compile(value)
    except re.error as error:
        raise ValidationError(_('Failed to compile: {0}').format(error))
    if not groups:
        return
    for group in groups:
        if group not in compiled.groupindex:
            raise ValidationError(
                _(
                    'Regular expression is missing named group "{0}", '
                    'the simplest way to define it is {1}.'
                ).format(
                    group,
                    '(?P<{}>.*)'.format(group)
                )
            )


def validate_bitmap(value):
    """Validate bitmap, based on django.forms.fields.ImageField"""
    if value is None:
        return

    # Ensure we have image object and content type
    # Pretty much copy from django.forms.fields.ImageField:
    if not hasattr(value.file, 'content_type'):
        # We need to get a file object for Pillow. We might have a path or we
        # might have to read the data into memory.
        if hasattr(value, 'temporary_file_path'):
            content = value.temporary_file_path()
        else:
            if hasattr(value, 'read'):
                content = BytesIO(value.read())
            else:
                content = BytesIO(value['content'])

        try:
            # load() could spot a truncated JPEG, but it loads the entire
            # image in memory, which is a DoS vector. See #3848 and #18520.
            image = Image.open(content)
            # verify() must be called immediately after the constructor.
            image.verify()

            # Annotating so subclasses can reuse it for their own validation
            value.file.image = image
            # Pillow doesn't detect the MIME type of all formats. In those
            # cases, content_type will be None.
            value.file.content_type = Image.MIME.get(image.format)
        except Exception:
            # Pillow doesn't recognize it as an image.
            six.reraise(ValidationError, ValidationError(
                _('Invalid image!'),
                code='invalid_image',
            ), sys.exc_info()[2])
        if hasattr(value.file, 'seek') and callable(value.file.seek):
            value.file.seek(0)

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
        val % {
            'file': 'file.po',
            '../file': 'file.po',
            '../../file': 'file.po',
            '../../../file': 'file.po',
            'line': '9',
            'branch': 'master'
        }
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

    # Block forbidden schemes as well as format strings
    if scheme.strip().lower() in FORBIDDEN_URL_SCHEMES or '%' in scheme:
        raise ValidationError(_('Forbidden URL scheme!'))


def clean_fullname(val):
    """Remove special chars from user full name."""
    if not val:
        return val
    val = val.strip()
    for i in range(0x20):
        val = val.replace(chr(i), '')
    return val


def validate_fullname(val):
    if val != clean_fullname(val):
        raise ValidationError(
            _('Please avoid using special chars in the full name.')
        )
    return val


def validate_file_extension(value):
    """Simple extension based validation for uploads."""
    ext = os.path.splitext(value.name)[1]
    if ext.lower() in FORBIDDEN_EXTENSIONS:
        raise ValidationError(_('Unsupported file format.'))
    return value


def validate_render(value, **kwargs):
    """Validates rendered template."""
    try:
        render_template(value, **kwargs)
    except Exception as err:
        raise ValidationError(
            _('Failed to render template: {}').format(err)
        )


def validate_username(value):
    if value.startswith('.'):
        raise ValidationError(
            _('Username can not start with a full stop.')
        )
    if not USERNAME_MATCHER.match(value):
        raise ValidationError(_(
            'Username may only contain letters, '
            'numbers or the following characters: @ . + - _'
        ))


def validate_email(value):
    validate_email_django(value)
    user_part = value.rsplit('@', 1)[0]
    if EMAIL_BLACKLIST.match(user_part):
        raise ValidationError(_('Enter a valid email address.'))
    if not re.match(settings.REGISTRATION_EMAIL_MATCH, value):
        raise ValidationError(_('This email address is not allowed.'))
