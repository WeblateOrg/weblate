# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

from io import BytesIO

from openpyxl import load_workbook

from weblate.formats.external import XlsxFormat
from weblate.formats.tests.test_formats import BaseFormatTest
from weblate.trans.tests.utils import get_test_file

XLSX_FILE = get_test_file("cs-mono.xlsx")
JAPANESE_FILE = get_test_file("ja.xlsx")


class XlsxFormatTest(BaseFormatTest):
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

    def test_japanese(self):
        storage = self.FORMAT.parse(JAPANESE_FILE)
        self.assertEqual(len(storage.all_units), 1)
        self.assertEqual(storage.all_units[0].target, "秒")
