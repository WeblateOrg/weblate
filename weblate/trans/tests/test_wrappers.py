# Copyright © Michal Karol <m.karol@neurosys.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for custom key separator wrapper."""

from unittest import TestCase

from weblate.formats.exporters import (
    BaseExporter,
    CSVExporter,
    I18NextV4Exporter,
    JSONExporter,
    PoExporter,
    XliffExporter,
)
from weblate.formats.ttkit import (
    CSVFormat,
    GoI18JSONFormat,
    I18NextFormat,
    JSONFormat,
    PoFormat,
    TranslationFormat,
    XliffFormat,
)
from weblate.trans.defines import DEFAULT_KEY_SEPARATOR
from weblate.trans.wrappers import (
    exporter_custom_key_separator_wrapper,
    file_format_custom_key_separator_wrapper,
)


class CustomKeySeparatorWrappersTest(TestCase):
    def test_file_format_custom_key_separator_wrapper_skips_non_json_classes(self):
        custom_key_separator = ":"
        for file_format_cls in [
            PoFormat,
            XliffFormat,
            TranslationFormat,
            CSVFormat,
        ]:
            new_file_format_cls = file_format_custom_key_separator_wrapper(
                file_format_cls, custom_key_separator
            )
            self.assertEqual(file_format_cls, new_file_format_cls)

    def test_file_format_custom_key_separator_wrapper_applies_to_json_classes(self):
        custom_key_separator = ":"
        for file_format_cls in [
            JSONFormat,
            I18NextFormat,
            GoI18JSONFormat,
        ]:
            new_file_format_cls = file_format_custom_key_separator_wrapper(
                file_format_cls, custom_key_separator
            )
            self.assertNotEqual(file_format_cls, new_file_format_cls)
            self.assertEqual(
                file_format_cls.get_class().UnitClass.IdClass.KEY_SEPARATOR,
                DEFAULT_KEY_SEPARATOR,
            )
            self.assertEqual(
                file_format_cls.unit_class.KEY_SEPARATOR, DEFAULT_KEY_SEPARATOR
            )
            self.assertEqual(
                new_file_format_cls.get_class().UnitClass.IdClass.KEY_SEPARATOR,
                custom_key_separator,
            )
            self.assertEqual(
                new_file_format_cls.unit_class.KEY_SEPARATOR, custom_key_separator
            )

    def test_exporter_custom_key_separator_wrapper_skips_non_json_classes(self):
        custom_key_separator = ":"
        for exporter_cls in [BaseExporter, PoExporter, XliffExporter, CSVExporter]:
            new_exporter_cls = exporter_custom_key_separator_wrapper(
                exporter_cls, custom_key_separator
            )
            self.assertEqual(exporter_cls, new_exporter_cls)

    def test_exporter_custom_key_separator_wrapper_applies_to_json_classes(self):
        custom_key_separator = ":"
        for exporter_cls in [
            JSONExporter,
            I18NextV4Exporter,
        ]:
            new_exporter_cls = exporter_custom_key_separator_wrapper(
                exporter_cls, custom_key_separator
            )
            self.assertNotEqual(exporter_cls, new_exporter_cls)
            self.assertEqual(
                exporter_cls.storage_class.UnitClass.IdClass.KEY_SEPARATOR,
                DEFAULT_KEY_SEPARATOR,
            )
            self.assertEqual(
                new_exporter_cls.storage_class.UnitClass.IdClass.KEY_SEPARATOR,
                custom_key_separator,
            )
