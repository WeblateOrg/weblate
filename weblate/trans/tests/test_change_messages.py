# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-FileCopyrightText: 2026 Samuel Gomes <samuel.esteves.gomes@tecnico.ulisboa.pt>
# SPDX-FileCopyrightText: 2026 Dinis Sales <dinis.sales@tecnico.ulisboa.pt>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for user-provided change message helpers."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from weblate.trans.change_messages import (
    CHANGE_MESSAGE_MAX_LENGTH,
    ChangeMessageField,
    normalize_change_message,
    validate_change_message,
)


class NormalizeChangeMessageTest(SimpleTestCase):
    def test_empty(self) -> None:
        self.assertEqual(normalize_change_message(""), "")
        self.assertEqual(normalize_change_message(None), "")

    def test_strips_surrounding_whitespace(self) -> None:
        self.assertEqual(normalize_change_message("  hello  "), "hello")

    def test_collapses_internal_whitespace(self) -> None:
        self.assertEqual(normalize_change_message("a\t\nb   c"), "a b c")

    def test_plain_message_unchanged(self) -> None:
        self.assertEqual(normalize_change_message("already clean"), "already clean")


class ValidateChangeMessageTest(SimpleTestCase):
    def test_valid_message_is_normalized(self) -> None:
        self.assertEqual(validate_change_message("  keep   tidy "), "keep tidy")

    def test_empty_is_allowed(self) -> None:
        self.assertEqual(validate_change_message(""), "")
        self.assertEqual(validate_change_message(None), "")

    def test_rejects_control_characters(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_change_message("bad\x00message")
        self.assertEqual(ctx.exception.code, "control_characters")

    def test_rejects_too_long_message(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_change_message("x" * (CHANGE_MESSAGE_MAX_LENGTH + 1))
        self.assertEqual(ctx.exception.code, "max_length")

    def test_accepts_message_at_limit(self) -> None:
        message = "x" * CHANGE_MESSAGE_MAX_LENGTH
        self.assertEqual(validate_change_message(message), message)


class ChangeMessageFieldTest(SimpleTestCase):
    def test_clean_normalizes_value(self) -> None:
        field = ChangeMessageField()
        self.assertEqual(field.clean("  spaced   note "), "spaced note")

    def test_clean_allows_empty(self) -> None:
        field = ChangeMessageField()
        self.assertEqual(field.clean(""), "")

    def test_clean_rejects_control_characters(self) -> None:
        field = ChangeMessageField()
        with self.assertRaises(ValidationError):
            field.clean("oops\x07bell")

    def test_field_is_optional(self) -> None:
        self.assertFalse(ChangeMessageField().required)
