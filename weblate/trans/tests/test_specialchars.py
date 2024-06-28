# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for special chars."""

from unittest import TestCase

from django.test.utils import override_settings

from weblate.lang.models import Language
from weblate.trans.specialchars import get_special_chars


class SpecialCharsTest(TestCase):
    def check_chars(self, language, count, matches, *args, **kwargs) -> None:
        result = get_special_chars(language, *args, **kwargs)
        chars = {x[2] for x in result}
        self.assertEqual(len(chars), count)
        for match in matches:
            self.assertIn(match, chars)

    def test_af(self) -> None:
        chars = list(get_special_chars(Language(code="af")))
        self.assertEqual(len(chars), 12)

    def test_cs(self) -> None:
        chars = list(get_special_chars(Language(code="cs")))
        self.assertEqual(len(chars), 11)

    def test_brx(self) -> None:
        chars = list(get_special_chars(Language(code="brx")))
        self.assertEqual(len(chars), 10)

    def test_brx_add(self) -> None:
        chars = list(get_special_chars(Language(code="brx"), "ahoj"))
        self.assertEqual(len(chars), 14)

    @override_settings(SPECIAL_CHARS=[chr(x) for x in range(256)])
    def test_settings(self) -> None:
        chars = list(get_special_chars(Language(code="cs")))
        self.assertEqual(len(chars), 263)

    def test_additional(self) -> None:
        self.check_chars(
            Language(code="cs"), 15, ["a", "h", "o", "j"], additional="ahoj"
        )

    def test_arrows(self) -> None:
        self.check_chars(Language(code="cs"), 13, ["→", "⇒"], source="→⇒→⇒")

    def test_arrows_rtl(self) -> None:
        self.check_chars(
            Language(code="ar", direction="rtl"), 14, ["←", "⇐"], source="→⇒→⇒"
        )
