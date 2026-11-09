# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""XLSX archive and shared-string conversion budgets."""

from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase, override_settings
from lxml import etree
from openpyxl import Workbook, load_workbook
from translate.storage.base import ParseError

from weblate.formats.external import XlsxFormat
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.limits import TranslationLimitError
from weblate.formats.xlsx_limits import prepare_xlsx_csv_row, validate_xlsx_archive
from weblate.utils.zip import ZipSafetyLimits

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


def make_workbook(rows: Iterable[Sequence[object]]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet()
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def make_shared_workbook(text: str, *, columns: int = 2, rows: int = 1) -> bytes:
    """Use a shared string without repeating its bytes in worksheet XML."""
    headers = ["source", "target", *(f"extra{index}" for index in range(columns - 2))]
    content = make_workbook([headers, *(["stub"] * columns for _ in range(rows))])
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    manifest_namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
    strings = etree.Element(
        f"{{{namespace}}}sst",
        nsmap={None: namespace},
        count=str(columns * rows),
        uniqueCount="1",
    )
    etree.SubElement(
        etree.SubElement(strings, f"{{{namespace}}}si"), f"{{{namespace}}}t"
    ).text = text
    output = BytesIO()
    with (
        ZipFile(BytesIO(content)) as source,
        ZipFile(output, "w", ZIP_DEFLATED) as target,
    ):
        for member in source.infolist():
            data = source.read(member)
            if member.filename == "[Content_Types].xml":
                manifest = etree.fromstring(data)
                etree.SubElement(
                    manifest,
                    f"{{{manifest_namespace}}}Override",
                    PartName="/xl/sharedStrings.xml",
                    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
                )
                data = etree.tostring(manifest)
            elif member.filename == "xl/worksheets/sheet1.xml":
                worksheet = etree.fromstring(data)
                for row in worksheet.findall(f".//{{{namespace}}}row"):
                    if row.attrib["r"] == "1":
                        continue
                    for cell in row:
                        for child in list(cell):
                            cell.remove(child)
                        cell.set("t", "s")
                        etree.SubElement(cell, f"{{{namespace}}}v").text = "0"
                data = etree.tostring(worksheet)
            target.writestr(member.filename, data)
        target.writestr("xl/sharedStrings.xml", etree.tostring(strings))
    return output.getvalue()


@override_settings(TRANSLATION_MAX_SIZE=2 * 1024 * 1024)
class XlsxLimitsTest(SimpleTestCase):
    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=1)
    def test_archive_limit_precedes_workbook_loading(self) -> None:
        content = make_workbook([["source", "target"], ["Hello", "Hola"]])
        with (
            patch("openpyxl.load_workbook") as loader,
            self.assertRaisesRegex(TranslationLimitError, "expanded size"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))
        loader.assert_not_called()

    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=100_000)
    def test_shared_strings_are_bounded_before_loading(self) -> None:
        content = make_shared_workbook("a" * 200_000)
        with (
            patch("openpyxl.load_workbook") as loader,
            self.assertRaises(TranslationLimitError),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))
        loader.assert_not_called()

    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=100_000)
    def test_repository_file_uses_same_expansion_budget(self) -> None:
        content = make_shared_workbook("a" * 200_000)
        with TemporaryDirectory() as directory:
            filename = Path(directory) / "test.xlsx"
            filename.write_bytes(content)
            with self.assertRaises(TranslationLimitError):
                XlsxFormat(filename)
            self.assertEqual(filename.read_bytes(), content)

    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=100_000)
    def test_wide_shared_string_row_is_rejected_before_csv_write(self) -> None:
        content = make_shared_workbook("a" * 64_000, columns=20)
        workbook = load_workbook(BytesIO(content), read_only=True)
        with (
            patch("openpyxl.load_workbook", return_value=workbook),
            patch.object(workbook, "close", wraps=workbook.close) as close,
            patch("weblate.formats.external.csv.writer") as writer,
            self.assertRaisesRegex(TranslationLimitError, "Converted workbook"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))
        writer.return_value.writerow.assert_called_once()
        close.assert_called_once_with()

    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=40_000)
    def test_conversion_budget_applies_across_rows(self) -> None:
        content = make_shared_workbook("a" * 8_000, rows=10)
        with (
            patch("weblate.formats.external.csv.writer") as writer,
            self.assertRaisesRegex(TranslationLimitError, "Converted workbook"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))
        self.assertEqual(writer.return_value.writerow.call_count, 3)

    def test_utf8_and_quoting_estimate_matches_csv_output(self) -> None:
        values = ["é", '"quoted"\n', None, 123, True]
        output = StringIO()
        csv.writer(output, dialect="unix").writerow(values)
        size = len(output.getvalue().encode("utf-8"))

        row, measured = prepare_xlsx_csv_row(values, size)

        self.assertEqual(measured, size)
        converted = StringIO()
        csv.writer(converted, dialect="unix").writerow(row)
        self.assertEqual(converted.getvalue(), output.getvalue())
        with self.assertRaises(TranslationLimitError):
            prepare_xlsx_csv_row(values, size - 1)

    def test_streamed_expansion_is_counted_independently_of_headers(self) -> None:
        stream = BytesIO(b"12345")
        with (
            patch("weblate.formats.xlsx_limits.ZipFile") as archive_class,
            self.assertRaises(TranslationLimitError),
        ):
            archive = archive_class.return_value.__enter__.return_value
            archive.infolist.return_value = [Mock(file_size=0)]
            archive.open.return_value = stream
            validate_xlsx_archive("test.xlsx", 3)
        self.assertTrue(stream.closed)

    def test_zip_member_count_is_bounded(self) -> None:
        content = make_workbook([["source", "target"], ["Hello", "Hola"]])
        with (
            patch(
                "weblate.formats.xlsx_limits.ZipSafetyLimits",
                return_value=ZipSafetyLimits(max_members=1),
            ),
            patch("openpyxl.load_workbook") as loader,
            self.assertRaisesRegex(TranslationLimitError, "too many entries"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))
        loader.assert_not_called()

    def test_streaming_row_limit_accepts_exact_boundary(self) -> None:
        content = make_workbook([["source", "target"], ["one", "uno"], ["two", "dos"]])
        with patch("weblate.formats.external.MAX_TRANSLATION_UNITS", 2):
            storage = XlsxFormat(NamedBytesIO("test.xlsx", content))
        self.assertEqual(len(storage.content_units), 2)

    def test_streaming_row_limit_rejects_excess_rows(self) -> None:
        content = make_workbook(
            [["source", "target"], ["one", "uno"], ["two", "dos"], ["three", "tres"]]
        )
        with (
            patch("weblate.formats.external.MAX_TRANSLATION_UNITS", 2),
            self.assertRaisesRegex(TranslationLimitError, "worksheet rows"),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", content))

    def test_sparse_row_gaps_cannot_bypass_read_limit(self) -> None:
        workbook = Workbook()
        worksheet = workbook.active
        self.assertIsNotNone(worksheet)
        if worksheet is None:
            self.fail("Expected active worksheet")
        worksheet.append(["source", "target"])
        worksheet.cell(row=100, column=1, value="far away")
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        with (
            patch("weblate.formats.external.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", output.getvalue()))

    def test_invalid_zip_is_clean_parse_error(self) -> None:
        with self.assertRaisesMessage(
            ParseError, "Could not open the workbook archive."
        ):
            XlsxFormat(NamedBytesIO("test.xlsx", b"not a ZIP file"))
