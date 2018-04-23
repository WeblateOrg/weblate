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

from __future__ import unicode_literals

from io import BytesIO
import os.path
import traceback

from appconf import AppConf

from django.utils.functional import cached_property

from weblate.formats.ttkit import AutoFormat
from weblate.trans.util import add_configuration_error
from weblate.utils.classloader import ClassLoader


class FileFormatLoader(ClassLoader):
    def __init__(self):
        super(FileFormatLoader, self).__init__('WEBLATE_FORMATS', False)

    @cached_property
    def autoload(self):
        result = []
        for fileformat in self.data.values():
            for autoload in fileformat.autoload:
                result.append((autoload, fileformat))
        return result

    def load_data(self):
        result = super(FileFormatLoader, self).load_data()

        for fileformat in list(result.values()):
            try:
                fileformat.get_class()
            except (AttributeError, ImportError):
                add_configuration_error(
                    'File format: {0}'.format(fileformat.format_id),
                    traceback.format_exc()
                )
                result.pop(fileformat.format_id)

        return result


FILE_FORMATS = FileFormatLoader()


class StringIOMode(BytesIO):
    """StringIO with mode attribute to make ttkit happy."""
    def __init__(self, filename, data):
        super(StringIOMode, self).__init__(data)
        self.mode = 'r'
        self.name = filename


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


class FormatsConf(AppConf):
    FORMATS = (
        'weblate.formats.ttkit.AutoFormat',
        'weblate.formats.ttkit.PoFormat',
        'weblate.formats.ttkit.PoMonoFormat',
        'weblate.formats.ttkit.TSFormat',
        'weblate.formats.ttkit.XliffFormat',
        'weblate.formats.ttkit.PoXliffFormat',
        'weblate.formats.ttkit.StringsFormat',
        'weblate.formats.ttkit.StringsUtf8Format',
        'weblate.formats.ttkit.PropertiesUtf8Format',
        'weblate.formats.ttkit.PropertiesUtf16Format',
        'weblate.formats.ttkit.PropertiesFormat',
        'weblate.formats.ttkit.JoomlaFormat',
        'weblate.formats.ttkit.PhpFormat',
        'weblate.formats.ttkit.RESXFormat',
        'weblate.formats.ttkit.AndroidFormat',
        'weblate.formats.ttkit.JSONFormat',
        'weblate.formats.ttkit.JSONNestedFormat',
        'weblate.formats.ttkit.WebExtensionJSONFormat',
        'weblate.formats.ttkit.I18NextFormat',
        'weblate.formats.ttkit.CSVFormat',
        'weblate.formats.ttkit.CSVSimpleFormat',
        'weblate.formats.ttkit.CSVSimpleFormatISO',
        'weblate.formats.ttkit.YAMLFormat',
        'weblate.formats.ttkit.RubyYAMLFormat',
        'weblate.formats.ttkit.DTDFormat',
        'weblate.formats.ttkit.WindowsRCFormat',
    )

    class Meta(object):
        prefix = 'WEBLATE'
