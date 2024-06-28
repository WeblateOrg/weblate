# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Captcha tests."""

from unittest import TestCase

from django.core.exceptions import ValidationError

from weblate.accounts.password_validation import CharsPasswordValidator


class ValidationTest(TestCase):
    def validate(self, password):
        validator = CharsPasswordValidator()
        return validator.validate(password)

    def test_chars_good(self) -> None:
        self.assertIsNone(self.validate("123"))

    def test_chars_whitespace(self) -> None:
        with self.assertRaises(ValidationError):
            self.validate(" \r\n\t")

    def test_chars_same(self) -> None:
        with self.assertRaises(ValidationError):
            self.validate("x" * 10)
