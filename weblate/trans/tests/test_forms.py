# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for form rendering."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils.safestring import SafeString

from weblate.trans.forms import PluralField, get_inherited_settings_label
from weblate.trans.validators import (
    MAX_TRANSLATION_ALTERNATIVES,
    MAX_TRANSLATION_TOTAL_LENGTH,
    validate_translation_text_length,
)


class TranslationSizeValidationTest(SimpleTestCase):
    def setUp(self) -> None:
        self.unit = Mock()
        self.unit.get_max_length.return_value = 100
        self.unit.translation.component.is_multivalue = True

    def test_rejects_too_many_alternatives(self) -> None:
        data = {
            f"target_{index}": "text"
            for index in range(MAX_TRANSLATION_ALTERNATIVES + 10)
        }
        field = PluralField()
        target = field.clean(field.widget.value_from_datadict(data, {}, "target"))

        self.assertEqual(len(target), MAX_TRANSLATION_ALTERNATIVES + 1)
        with self.assertRaisesMessage(ValidationError, "Translation text too long!"):
            validate_translation_text_length(self.unit, target)

    def test_rejects_excessive_aggregate_length(self) -> None:
        target = ["x" * 2000] * (MAX_TRANSLATION_TOTAL_LENGTH // 2000 + 1)

        with self.assertRaisesMessage(ValidationError, "Translation text too long!"):
            validate_translation_text_length(self.unit, target)

    def test_plural_length_is_not_aggregated(self) -> None:
        self.unit.translation.component.is_multivalue = False
        target = ["x" * 2000] * (MAX_TRANSLATION_TOTAL_LENGTH // 2000 + 1)

        validate_translation_text_length(self.unit, target)


class FormRenderingTest(SimpleTestCase):
    def test_icon_help_text_escapes_title_attribute(self) -> None:
        # Safe help text must still be escaped when reused in an HTML attribute.
        field = SimpleNamespace(
            auto_id="id_fuzzy",
            field=SimpleNamespace(help_as_icon=True),
            help_text=SafeString(
                'Quote "Needs editing" and <strong>HTML help text</strong>.'
            ),
        )

        rendered = render_to_string(
            "bootstrap5/layout/help_text.html", {"field": field}
        )

        self.assertIn(
            'title="Quote &quot;Needs editing&quot; and '
            '&lt;strong&gt;HTML help text&lt;/strong&gt;."',
            rendered,
        )
        self.assertNotIn('title="Quote "Needs editing"', rendered)
        self.assertNotIn("<strong>HTML help text</strong>", rendered)


class InheritedSettingsLabelTest(SimpleTestCase):
    def test_inherited_settings_labels_are_complete_translatable_strings(self) -> None:
        self.assertEqual(
            get_inherited_settings_label("workspace"), "Inherit from workspace"
        )
        self.assertEqual(
            get_inherited_settings_label("project"), "Inherit from project"
        )
        self.assertEqual(
            get_inherited_settings_label("category"), "Inherit from category"
        )
