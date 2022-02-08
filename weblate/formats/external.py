#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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
from io import BytesIO, StringIO
from typing import Callable, Optional
from zipfile import BadZipFile

from django.utils.translation import gettext_lazy as _
from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, TYPE_STRING
from translate.storage.csvl10n import csv

from weblate.formats.helpers import BytesIOMode
from weblate.formats.ttkit import CSVFormat


class XlsxFormat(CSVFormat):
    name = _("Excel Open XML")
    format_id = "xlsx"
    autoload = ("*.xlsx",)

    def write_cell(self, worksheet, column: int, row: int, value: str):
        cell = worksheet.cell(column=column, row=row)
        cell.value = value
        # Set the data_type after value to override function auto-detection
        cell.data_type = TYPE_STRING
        return cell

    def save_content(self, handle):
        workbook = Workbook()
        worksheet = workbook.active

        worksheet.title = self.store.targetlanguage or "Weblate"

        # write headers
        for column, field in enumerate(self.store.fieldnames):
            self.write_cell(worksheet, column + 1, 1, field)

        for row, unit in enumerate(self.store.units):
            data = unit.todict()

            for column, field in enumerate(self.store.fieldnames):
                self.write_cell(
                    worksheet,
                    column + 1,
                    row + 2,
                    ILLEGAL_CHARACTERS_RE.sub("", data[field]),
                )

        workbook.save(handle)

    @staticmethod
    def serialize(store):
        # store is CSV (csvfile) here
        output = BytesIO()
        XlsxFormat(store).save_content(output)
        return output.getvalue()

    def parse_store(self, storefile):
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
    def create_new_file(
        cls,
        filename: str,
        language: str,
        base: str,
        callback: Optional[Callable] = None,
    ):
        """Handle creation of new translation file."""
        if not base:
            raise ValueError("Not supported")
        # Parse file
        store = cls(base)
        if callback:
            callback(store)
        store.untranslate_store(language)
        with open(filename, "wb") as handle:
            XlsxFormat(store.store).save_content(handle)
