# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared translation-file size and content-unit acceptance limits."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from openpyxl import Workbook

from weblate.formats.auto import try_load
from weblate.formats.external import XlsxFormat
from weblate.formats.helpers import NamedBytesIO
from weblate.formats.limits import (
    MAX_TRANSLATION_UNITS,
    TranslationLimitError,
    check_translation_file_size,
    translation_max_size,
)
from weblate.formats.ttkit import JSONFormat, PoFormat
from weblate.formats.txt import TextParser
from weblate.trans.exceptions import FileParseError
from weblate.trans.models.translation import read_translation_upload
from weblate.trans.tests.test_views import ViewTestCase

if TYPE_CHECKING:
    from weblate.formats.base import TranslationFormat
    from weblate.trans.models import Component


class TranslationLimitsTest(SimpleTestCase):
    @override_settings(TRANSLATION_MAX_SIZE=None, TRANSLATION_UPLOAD_MAX_SIZE=8)
    def test_size_default_follows_upload_setting(self) -> None:
        self.assertEqual(translation_max_size(), 8)
        with (
            patch.object(JSONFormat, "load") as parse,
            self.assertRaisesRegex(TranslationLimitError, "8 bytes"),
        ):
            JSONFormat(NamedBytesIO("source.json", b'{"a":"b"}'))
        parse.assert_not_called()

    @override_settings(TRANSLATION_MAX_SIZE=9, TRANSLATION_UPLOAD_MAX_SIZE=8)
    def test_explicit_size_and_independent_upload_limit(self) -> None:
        content = b'{"a":"b"}'
        storage: TranslationFormat = JSONFormat(
            NamedBytesIO("source.json", content), is_template=True
        )
        self.assertEqual(len(storage.content_units), 1)
        with self.assertRaises(ValidationError):
            read_translation_upload(NamedBytesIO("source.json", content))

    @override_settings(TRANSLATION_MAX_SIZE=8, TRANSLATION_UPLOAD_MAX_SIZE=20)
    def test_upload_obeys_smaller_parse_limit(self) -> None:
        with self.assertRaises(ValidationError):
            read_translation_upload(NamedBytesIO("source.json", b'{"a":"b"}'))

    @override_settings(TRANSLATION_MAX_SIZE=4)
    def test_stream_size_preserves_position(self) -> None:
        stream = NamedBytesIO("source.txt", b"12345")
        stream.seek(4)
        with self.assertRaises(TranslationLimitError):
            check_translation_file_size(stream)
        self.assertEqual(stream.tell(), 4)
        check_translation_file_size(NamedBytesIO("source.txt", b"1234"))

    @override_settings(TRANSLATION_MAX_SIZE=4)
    def test_repository_file_rejected_before_parser(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            path.write_bytes(b'{"a":"b"}')
            with (
                patch.object(JSONFormat, "load") as parse,
                self.assertRaises(TranslationLimitError),
            ):
                JSONFormat(path)
            parse.assert_not_called()

    @override_settings(TRANSLATION_MAX_SIZE=4)
    def test_metadata_file_counts_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "description.txt"
            path.write_text("ééé", encoding="utf-8")
            with self.assertRaises(TranslationLimitError):
                TextParser(path)

    @override_settings(TRANSLATION_MAX_SIZE=4)
    def test_bilingual_update_checks_input_and_template(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "translation.po"
            template = Path(directory) / "template.pot"
            for oversized in (path, template):
                with self.subTest(oversized=oversized.name):
                    path.write_bytes(b"1234")
                    template.write_bytes(b"1234")
                    oversized.write_bytes(b"12345")
                    before = path.read_bytes()
                    with (
                        patch.object(PoFormat, "do_bilingual_update") as parse,
                        self.assertRaises(TranslationLimitError),
                    ):
                        PoFormat.update_bilingual(str(path), str(template))
                    parse.assert_not_called()
                    self.assertEqual(path.read_bytes(), before)

    @override_settings(TRANSLATION_MAX_SIZE=4)
    def test_autodetection_stops_before_trying_formats(self) -> None:
        with (
            patch("weblate.formats.auto.formats_iter") as formats,
            self.assertRaises(TranslationLimitError),
        ):
            try_load("source.json", b'{"a":"b"}', JSONFormat, None)
        formats.assert_not_called()

    def test_logical_units_are_bounded(self) -> None:
        content = b'{"one":"One","two":"Two","three":"Three"}'
        storage: TranslationFormat = JSONFormat(
            NamedBytesIO("source.json", content), is_template=True
        )
        with patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 2):
            with self.assertRaisesRegex(TranslationLimitError, "2 strings"):
                _ = storage.content_units
            with self.assertRaises(TranslationLimitError):
                _ = storage.template_units

    def test_headers_do_not_count_as_content(self) -> None:
        content = b'msgid ""\nmsgstr ""\n\nmsgid "One"\nmsgstr "Uno"\n'
        with patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 1):
            storage = PoFormat(NamedBytesIO("source.po", content))
            self.assertEqual(len(storage.content_units), 1)

    def test_monolingual_extras_count_toward_file_limit(self) -> None:
        template: TranslationFormat = JSONFormat(
            NamedBytesIO("source.json", b'{"one":"One"}'), is_template=True
        )
        storage: TranslationFormat = JSONFormat(
            NamedBytesIO("target.json", b'{"one":"Uno","two":"Dos","three":"Tres"}'),
            template_store=template,
        )
        with (
            patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            _ = storage.content_units

    def test_converted_workbook_uses_shared_unit_limit(self) -> None:
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet()
        sheet.append(["source", "target"])
        for index in range(3):
            sheet.append([f"Source {index}", f"Target {index}"])
        stream = NamedBytesIO("test.xlsx", b"")
        workbook.save(stream)
        workbook.close()
        stream.seek(0)
        storage = XlsxFormat(stream)
        with (
            patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            _ = storage.content_units

    def test_autodetection_does_not_bypass_unit_limit(self) -> None:
        content = b'{"one":"One","two":"Two","three":"Three"}'
        with (
            patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 2),
            self.assertRaises(TranslationLimitError),
        ):
            try_load("source.json", content, JSONFormat, None, is_template=True)

    def test_full_size_component_at_unit_boundary(self) -> None:
        content = json.dumps(
            {str(index): f"String {index}" for index in range(MAX_TRANSLATION_UNITS)}
        ).encode()
        storage: TranslationFormat = JSONFormat(
            NamedBytesIO("source.json", content), is_template=True
        )
        self.assertEqual(len(storage.content_units), MAX_TRANSLATION_UNITS)


class RepositoryTranslationLimitsTest(ViewTestCase):
    def create_component(self) -> Component:
        return self.create_json_intermediate()

    def test_sync_rejects_store_before_database_changes(self) -> None:
        translation = self.get_translation()
        before = list(translation.unit_set.order_by("pk").values_list("pk", "target"))
        self.assertGreater(len(before), 1)
        with (
            patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 1),
            self.assertRaises(FileParseError),
        ):
            translation.update_units_from_store(user=self.user, author=self.user)
        self.assertEqual(
            list(translation.unit_set.order_by("pk").values_list("pk", "target")),
            before,
        )

    def test_source_and_intermediate_size_limits(self) -> None:
        with override_settings(TRANSLATION_MAX_SIZE=1):
            with self.assertRaises(TranslationLimitError):
                self.component.load_template_store()
            with self.assertRaises(TranslationLimitError):
                self.component.load_intermediate_store()

    def test_source_and_intermediate_unit_limits(self) -> None:
        with patch("weblate.formats.limits.MAX_TRANSLATION_UNITS", 1):
            with self.assertRaises(TranslationLimitError):
                self.component.load_template_store()
            with self.assertRaises(TranslationLimitError):
                self.component.load_intermediate_store()
