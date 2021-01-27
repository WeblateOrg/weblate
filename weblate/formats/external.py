#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import os
import re
from io import BytesIO, StringIO
from zipfile import BadZipFile

from django.utils.translation import gettext_lazy as _
from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import TYPE_STRING
from translate.storage.csvl10n import csv

from weblate.formats.helpers import BytesIOMode
from weblate.formats.ttkit import CSVFormat

# use the same relugar expression as in openpyxl.cell
# to remove illegal characters
ILLEGAL_CHARACTERS_RE = re.compile(r"[\000-\010]|[\013-\014]|[\016-\037]")


class XlsxFormat(CSVFormat):
    name = _("Excel Open XML")
    format_id = "xlsx"
    autoload = ("*.xlsx",)

    def save_content(self, handle):
        workbook = Workbook()
        worksheet = workbook.active

        worksheet.title = self.store.targetlanguage or "Weblate"

        # write headers
        for column, field in enumerate(self.store.fieldnames):
            worksheet.cell(column=1 + column, row=1, value=field)

        for row, unit in enumerate(self.store.units):
            data = unit.todict()

            for column, field in enumerate(self.store.fieldnames):
                cell = worksheet.cell(column=1 + column, row=2 + row)
                cell.data_type = TYPE_STRING
                cell.value = ILLEGAL_CHARACTERS_RE.sub("", data[field])
        workbook.save(handle)

    @staticmethod
    def serialize(store):
        # store is CSV (csvfile) here
        output = BytesIO()
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

        output = StringIO()

        writer = csv.writer(output, dialect="unix")

        for row in worksheet.rows:
            writer.writerow([cell.value for cell in row])

        if isinstance(storefile, str):
            name = os.path.basename(storefile) + ".csv"
        else:
            name = os.path.basename(storefile.name) + ".csv"

        # return the new csv as bytes
        content = output.getvalue().encode()

        # Load the file as CSV
        return super().parse_store(BytesIOMode(name, content))

    @staticmethod
    def mimetype():
        """Return most common mime type for format."""
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "xlsx"

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        if not base:
            raise ValueError("Not supported")
        # Parse file
        store = cls.parse_store(base)
        cls.untranslate_store(store, language)
        with open(filename, "wb") as handle:
            XlsxFormat(store).save_content(handle)
