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
"""File format specific behavior."""

from io import BytesIO
from unittest import skipIf

import translate.__version__
from openpyxl import load_workbook

from weblate.formats.external import XlsxFormat
from weblate.formats.tests.test_formats import AutoFormatTest
from weblate.trans.tests.utils import get_test_file

XLSX_FILE = get_test_file("cs-mono.xlsx")
JAPANESE_FILE = get_test_file("ja.xlsx")


class XlsxFormatTest(AutoFormatTest):
    FORMAT = XlsxFormat
    FILE = XLSX_FILE
    MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    EXT = "xlsx"
    COUNT = 4
    MASK = "*/translations.xlsx"
    EXPECTED_PATH = "cs_CZ/translations.xlsx"
    FIND = "HELLO"
    FIND_MATCH = "Hello, world!\r\n"
    MATCH = b"PK"
    NEW_UNIT_MATCH = b"PK"
    BASE = XLSX_FILE
    EXPECTED_FLAGS = ""

    def assert_same(self, newdata, testdata):
        newworkbook = load_workbook(BytesIO(newdata))
        testworkbook = load_workbook(BytesIO(testdata))
        self.assertEqual(len(newworkbook.worksheets), len(testworkbook.worksheets))
        self.assertEqual(
            list(newworkbook.active.values), list(testworkbook.active.values)
        )

    @skipIf(translate.__version__.ver <= (3, 5, 4), "broken in older translate-toolkit")
    def test_japanese(self):
        storage = self.FORMAT.parse(JAPANESE_FILE)
        self.assertEqual(len(storage.all_units), 1)
        self.assertEqual(storage.all_units[0].target, "秒")
