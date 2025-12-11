# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for various helper utilities."""

from django.test import SimpleTestCase

from weblate.auth.utils import format_address


class FormatAddressTestCase(SimpleTestCase):
    def test_unicode(self) -> None:
        self.assertEqual(
            format_address("Michal Čihař", "michal@weblate.org"),
            "Michal Čihař <michal@weblate.org>",
        )

    def test_invalid(self) -> None:
        self.assertEqual(
            format_address("<a>", "noreply@example.com"), "a <noreply@example.com>"
        )

    def test_value_error(self) -> None:
        with self.assertRaises(ValueError):
            format_address("x", ".@example.com")
