# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bound CSV store growth during parsing, including fallback detection."""

from __future__ import annotations

import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.test import SimpleTestCase
from translate.storage.base import ParseError

from weblate.formats.auto import AutodetectFormat, try_load
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.limits import MAX_TRANSLATION_UNITS, TranslationLimitError
from weblate.formats.ttkit import (
    CSVFormat,
    CSVSimpleFormat,
    WeblateCSVFile,
    WeblateCSVUnit,
)

if TYPE_CHECKING:
    from weblate.formats.base import TranslationFormat


class CSVRowLimitTest(SimpleTestCase):
    def test_parser_stops_building_units_at_limit(self) -> None:
        store = WeblateCSVFile()
        content = b"source,target\none,uno\ntwo,dos\nthree,tres\nfour,cuatro\n"
        with (
            patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2),
            self.assertRaisesRegex(TranslationLimitError, "2 data rows"),
        ):
            store.parse(content)

        self.assertEqual(len(store.units), 2)
        self.assertEqual([unit.source for unit in store.units], ["one", "two"])

    def test_header_and_multiline_values_do_not_consume_extra_rows(self) -> None:
        content = b'source,target\n"first\nsecond","uno\ndos"\nthree,tres\n'
        with patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2):
            storage = CSVFormat(NamedBytesIO("test.csv", content))
        self.assertEqual(len(storage.content_units), 2)
        self.assertEqual(storage.content_units[0].source, "first\nsecond")

    def test_empty_field_rows_consume_parser_budget(self) -> None:
        store = WeblateCSVFile()
        with (
            patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            store.parse(b"source,target\none,uno\n,\n,\n")
        self.assertEqual(len(store.units), 2)

    def test_blank_lines_do_not_consume_parser_budget(self) -> None:
        store = WeblateCSVFile()
        with patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2):
            store.parse(b"source,target\n\none,uno\n\ntwo,dos\n\n")
        self.assertEqual(len(store.units), 2)

    def test_standard_and_simple_csv_use_same_limit(self) -> None:
        for format_class in (CSVFormat, CSVSimpleFormat):
            with (
                self.subTest(format=format_class.format_id),
                patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2),
                self.assertRaises(TranslationLimitError),
            ):
                format_class(
                    NamedBytesIO("test.csv", b"one,uno\ntwo,dos\nthree,tres\n")
                )

    def test_autodetection_stops_at_row_limit(self) -> None:
        content = b"source,target\none,uno\ntwo,dos\nthree,tres\n"
        with (
            patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            AutodetectFormat(NamedBytesIO("test.csv", content))

    def test_plural_rows_are_bounded_before_logical_grouping(self) -> None:
        content = (
            b"source,target,source_plural_form,target_plural_form,id_hash\n"
            b"file,archivo,0,0,0x0000000000000123\n"
            b"files,archivos,1,1,0x0000000000000123\n"
            b"files,archivos,1,2,0x0000000000000123\n"
        )
        storage: TranslationFormat = CSVFormat(NamedBytesIO("test.csv", content))
        self.assertEqual(len(storage.content_units), 1)
        with (
            patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            CSVFormat(NamedBytesIO("test.csv", content))

    def test_try_load_does_not_retry_an_oversized_csv(self) -> None:
        content = b"source,target\none,uno\ntwo,dos\nthree,tres\n"
        with (
            patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 2),
            patch.object(AutodetectFormat, "parse_store") as fallback,
            self.assertRaises(TranslationLimitError),
        ):
            try_load("test.csv", content, CSVFormat, None)
        fallback.assert_not_called()

    def test_failed_parse_does_not_limit_programmatic_store_updates(self) -> None:
        store = WeblateCSVFile()
        with (
            patch("weblate.formats.ttkit.MAX_TRANSLATION_UNITS", 1),
            self.assertRaises(TranslationLimitError),
        ):
            store.parse(b"source,target\none,uno\ntwo,dos\n")
        unit = WeblateCSVUnit()
        unit.source = "Added by a writer"
        store.addunit(unit)
        self.assertEqual(len(store.units), 2)

    def test_real_row_ceiling_accepts_boundary_and_rejects_one_more(self) -> None:
        content = b"source,target\n" + b"a,b\n" * MAX_TRANSLATION_UNITS
        store = WeblateCSVFile()
        store.parse(content)
        self.assertEqual(len(store.units), MAX_TRANSLATION_UNITS)
        store = WeblateCSVFile()
        with self.assertRaises(TranslationLimitError):
            store.parse(content + b"c,d\n")
        self.assertEqual(len(store.units), MAX_TRANSLATION_UNITS)

    def test_compressed_csv_keeps_tighter_extraction_limit(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv.gz"
            path.write_bytes(gzip.compress(b"source,target\none,uno\ntwo,dos\n"))
            with (
                patch("weblate.formats.auto.MAX_EXTRACTED_UNITS", 1),
                self.assertRaisesRegex(ParseError, "unit extraction limit"),
            ):
                AutodetectFormat(str(path))
