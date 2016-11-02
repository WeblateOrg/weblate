# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import re

from django.db.models import CharField, ImageField
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _


ALLOWED_IMAGES = (
    'image/jpeg',
    'image/png',
)


def validate_re(value):
    try:
        re.compile(value)
    except re.error as error:
        raise ValidationError(_('Failed to compile: {0}').format(error))


def validate_bitmap(value):
    """Validates bitmap, based on django.forms.fields.ImageField"""
    if value is None:
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


class RegexField(CharField):
    default_validators = [validate_re]


class ScreenshotField(ImageField):
    """File field which forces certain image types"""
    default_validators = [validate_bitmap]
