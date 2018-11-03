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
"""External file format specific behavior."""
from __future__ import unicode_literals

import csv
import os
import re

try:
    # python 3 exception
    from zipfile import BadZipFile
except ImportError:
    # python 2 exception
    from zipfile import BadZipfile as BadZipFile

import six
from django.utils.translation import ugettext_lazy as _

from openpyxl import Workbook, load_workbook

from weblate.formats.helpers import StringIOMode
from weblate.formats.ttkit import CSVFormat

# use the same relugar expression as in openpyxl.cell
# to remove illegal characters
ILLEGAL_CHARACTERS_RE = re.compile(r'[\000-\010]|[\013-\014]|[\016-\037]')


class XlsxFormat(CSVFormat):
    name = _('Excel Open XML')
    format_id = 'xlsx'
    autoload = ('.xlsx',)

    def save_content(self, handle):
        workbook = Workbook()
        worksheet = workbook.active

        worksheet.title = self.store.targetlanguage

        # write headers
        for column, field in enumerate(self.store.fieldnames):
            worksheet.cell(
                column=1 + column,
                row=1,
                value=field,
            )

        for row, unit in enumerate(self.store.units):
            data = unit.todict()

            for column, field in enumerate(self.store.fieldnames):
                worksheet.cell(
                    column=1 + column,
                    row=2 + row,
                ).set_explicit_value(
                    ILLEGAL_CHARACTERS_RE.sub('', data[field]),
                    data_type="s"
                )
        workbook.save(handle)

    @staticmethod
    def serialize(store):
        # store is CSV (csvfile) here
        output = six.BytesIO()
        XlsxFormat(store).save_content(output)
        return output.getvalue()

    @classmethod
    def parse_store(cls, storefile):
        # try to load the given file via openpyxl
        # catch at least the BadZipFile exception if an unsupported
        # file has been given
        try:
            workbook = load_workbook(filename=storefile)
            worksheet = workbook.active
        except BadZipFile:
            return None, None

        if six.PY3:
            output = six.StringIO()
        else:
            output = six.BytesIO()

        writer = csv.writer(output)

        for row in worksheet.rows:
            writer.writerow([cls.encode(cell.value) for cell in row])

        name = os.path.basename(storefile.name) + ".csv"

        # return the new csv as bytes
        content = output.getvalue()

        if six.PY3:
            content = content.encode("utf-8")

        # Load the file as CSV
        return super(XlsxFormat, cls).parse_store(StringIOMode(name, content))

    @staticmethod
    def encode(value):
        if value is None:
            return value
        if six.PY2:
            return value.encode("utf-8")
        return value
