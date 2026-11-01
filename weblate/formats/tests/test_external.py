# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File format specific behavior."""

from __future__ import annotations

import tempfile
from io import BytesIO
from unittest.mock import Mock, patch
from zipfile import ZipFile

from django.test import SimpleTestCase
from openpyxl import Workbook, load_workbook

from weblate.formats.external import XlsxFormat
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.tests.test_formats import BaseFormatTest
from weblate.trans.tests.utils import get_test_file

XLSX_FILE = get_test_file("cs-mono.xlsx")
JAPANESE_FILE = get_test_file("ja.xlsx")
FRENCH_FILE = get_test_file("fr.xlsx")


class XlsxStreamingTest(SimpleTestCase):
    @staticmethod
    def get_content(*, formatting: bool = False) -> bytes:
        workbook = Workbook()
        worksheet = workbook.active
        if worksheet is None:
            msg = "Workbook without an active sheet"
            raise AssertionError(msg)
        worksheet.append(["source", "target", "context"])
        worksheet.append(["Hello", "Ahoj", "greeting"])
        worksheet.append(["Goodbye"])
        if formatting:
            worksheet.cell(row=10, column=8).number_format = "@"
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def assert_content(self, content: bytes) -> None:
        storage = XlsxFormat(NamedBytesIO("test.xlsx", content))
        self.assertEqual(
            [(unit.source, unit.target, unit.context) for unit in storage.all_units],
            [("Hello", "Ahoj", "greeting"), ("Goodbye", "", "")],
        )

    def test_trailing_empty_cells(self) -> None:
        self.assert_content(self.get_content())

    def test_formatting_only_cells(self) -> None:
        self.assert_content(self.get_content(formatting=True))

    def test_incorrect_dimensions(self) -> None:
        content = self.get_content()
        for dimension in (b"A1:A1", b"A1:H20"):
            with self.subTest(dimension=dimension):
                output = BytesIO()
                with (
                    ZipFile(BytesIO(content)) as source,
                    ZipFile(output, "w") as target,
                ):
                    for member in source.infolist():
                        data = source.read(member)
                        if member.filename == "xl/worksheets/sheet1.xml":
                            self.assertIn(b'<dimension ref="A1:C3"/>', data)
                            data = data.replace(
                                b'<dimension ref="A1:C3"/>',
                                b'<dimension ref="' + dimension + b'"/>',
                            )
                        target.writestr(member, data)
                self.assert_content(output.getvalue())

    def test_close_workbook(self) -> None:
        content = self.get_content()
        workbook = load_workbook(BytesIO(content), read_only=True)
        with (
            patch("openpyxl.load_workbook", return_value=workbook) as loader,
            patch.object(workbook, "close", wraps=workbook.close) as close,
        ):
            self.assert_content(content)
            self.assertTrue(loader.call_args.kwargs["read_only"])
            close.assert_called_once_with()

    def test_close_workbook_on_iteration_error(self) -> None:
        content = self.get_content()
        workbook = load_workbook(BytesIO(content), read_only=True)
        worksheet = workbook.active
        self.assertIsNotNone(worksheet)
        with (
            patch("openpyxl.load_workbook", return_value=workbook),
            patch.object(workbook, "close", wraps=workbook.close) as close,
            patch.object(worksheet, "iter_rows", side_effect=ValueError("invalid row")),
            self.assertRaisesMessage(ValueError, "invalid row"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))
        close.assert_called_once_with()

    def test_close_workbook_without_active_sheet(self) -> None:
        workbook = Mock(active=None)
        with (
            patch("openpyxl.load_workbook", return_value=workbook),
            self.assertRaisesMessage(TypeError, "Workbook without an active sheet!"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", self.get_content()))
        workbook.close.assert_called_once_with()


class XlsxFormatTest(BaseFormatTest):
    format_class = XlsxFormat
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

    def assert_same(self, newdata: bytes, testdata: bytes) -> None:
        newworkbook = load_workbook(BytesIO(newdata))
        testworkbook = load_workbook(BytesIO(testdata))
        self.assertEqual(len(newworkbook.worksheets), len(testworkbook.worksheets))
        self.assertIsNotNone(newworkbook.active)
        self.assertIsNotNone(testworkbook.active)
        # To make type checker happy
        if newworkbook.active is None or testworkbook.active is None:
            raise TypeError
        self.assertEqual(
            list(newworkbook.active.values),
            list(testworkbook.active.values),
        )

    def test_japanese(self) -> None:
        storage = self.format_class(JAPANESE_FILE)
        self.assertEqual(len(storage.all_units), 1)
        self.assertEqual(storage.all_units[0].target, "秒")
        with tempfile.NamedTemporaryFile(suffix="xlsx") as temp_file:
            storage.save_atomic(temp_file.name, storage.save_content)

    def test_fr(self) -> None:
        storage = self.format_class(FRENCH_FILE)
        self.assertEqual(len(storage.all_units), 4)
        self.assertEqual(storage.all_units[0].target, "Traitement A")
        with tempfile.NamedTemporaryFile(suffix="xlsx") as temp_file:
            storage.save_atomic(temp_file.name, storage.save_content)

    def test_encoding(self) -> None:
        # check that the encoding is always utf-8
        storage = self.format_class(XLSX_FILE)
        self.assertEqual(storage.get_encoding(), "utf-8")
