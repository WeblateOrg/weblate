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

import os.path

from appconf import AppConf

from django.utils.functional import cached_property

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
        'weblate.formats.AutoFormat',
        'weblate.formats.PoFormat',
        'weblate.formats.PoMonoFormat',
        'weblate.formats.TSFormat',
        'weblate.formats.XliffFormat',
        'weblate.formats.PoXliffFormat',
        'weblate.formats.StringsFormat',
        'weblate.formats.StringsUtf8Format',
        'weblate.formats.PropertiesUtf8Format',
        'weblate.formats.PropertiesUtf16Format',
        'weblate.formats.PropertiesFormat',
        'weblate.formats.JoomlaFormat',
        'weblate.formats.PhpFormat',
        'weblate.formats.RESXFormat',
        'weblate.formats.AndroidFormat',
        'weblate.formats.JSONFormat',
        'weblate.formats.JSONNestedFormat',
        'weblate.formats.WebExtensionJSONFormat',
        'weblate.formats.I18NextFormat',
        'weblate.formats.CSVFormat',
        'weblate.formats.CSVSimpleFormat',
        'weblate.formats.CSVSimpleFormatISO',
        'weblate.formats.YAMLFormat',
        'weblate.formats.RubyYAMLFormat',
        'weblate.formats.DTDFormat',
        'weblate.formats.WindowsRCFormat',
    )

    class Meta(object):
        prefix = 'WEBLATE'
