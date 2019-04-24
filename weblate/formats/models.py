# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from appconf import AppConf

from django.utils.functional import cached_property

import six

from weblate.trans.util import (
    add_configuration_error, delete_configuration_error,
)
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
            error_name = 'File format: {0}'.format(fileformat.format_id)
            try:
                fileformat.get_class()
                delete_configuration_error(error_name)
            except (AttributeError, ImportError) as error:
                result.pop(fileformat.format_id)
                if fileformat.format_id == 'rc' and six.PY3:
                    continue
                add_configuration_error(error_name, str(error))

        return result


FILE_FORMATS = FileFormatLoader()


class FormatsConf(AppConf):
    FORMATS = (
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
        'weblate.formats.external.XlsxFormat',
        'weblate.formats.txt.AppStoreFormat',
    )

    class Meta(object):
        prefix = 'WEBLATE'
