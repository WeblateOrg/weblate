
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
"""translate-toolkit based file format wrappers."""

from __future__ import unicode_literals

from io import BytesIO
import os.path

from django.utils.translation import ugettext_lazy as _

from translate.storage import factory

from weblate.formats.base import FileFormat
from weblate.formats.models import FILE_FORMATS


def detect_filename(filename):
    """Filename based format autodetection"""
    name = os.path.basename(filename)
    for autoload, storeclass in FILE_FORMATS.autoload:
        if not isinstance(autoload, tuple) and name.endswith(autoload):
            return storeclass
        elif (name.startswith(autoload[0]) and
              name.endswith(autoload[1])):
            return storeclass
    return None


def try_load(filename, content, original_format, template_store):
    """Try to load file by guessing type"""
    formats = [original_format, AutoFormat]
    detected_format = detect_filename(filename)
    if detected_format is not None:
        formats.insert(0, detected_format)
    failure = Exception('Bug!')
    for file_format in formats:
        if file_format.monolingual in (True, None) and template_store:
            try:
                result = file_format.parse(
                    StringIOMode(filename, content),
                    template_store
                )
                # Skip if there is not translated unit
                # this can easily happen when importing bilingual
                # storage which can be monolingual as well
                if list(result.iterate_merge(False)):
                    return result
            except Exception as error:
                failure = error
        if file_format.monolingual in (False, None):
            try:
                return file_format.parse(StringIOMode(filename, content))
            except Exception as error:
                failure = error

    raise failure


class AutoFormat(FileFormat):
    name = _('Automatic detection')
    format_id = 'auto'

    @classmethod
    def parse(cls, storefile, template_store=None, language_code=None):
        """Parse store and returns FileFormat instance.

        First attempt own autodetection, then fallback to ttkit.
        """
        if hasattr(storefile, 'read'):
            filename = getattr(storefile, 'name', None)
        else:
            filename = storefile
        if filename is not None:
            storeclass = detect_filename(filename)
            if storeclass is not None:
                return storeclass(storefile, template_store, language_code)
        return cls(storefile, template_store, language_code)

    @classmethod
    def parse_store(cls, storefile):
        """Directly loads using translate-toolkit."""
        return factory.getobject(storefile)

    @classmethod
    def get_class(cls):
        return None


class StringIOMode(BytesIO):
    """StringIO with mode attribute to make ttkit happy."""
    def __init__(self, filename, data):
        super(StringIOMode, self).__init__(data)
        self.mode = 'r'
        self.name = filename
