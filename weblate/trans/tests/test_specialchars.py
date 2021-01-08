#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for special chars."""


from unittest import TestCase

from django.test.utils import override_settings

from weblate.lang.models import Language
from weblate.trans.specialchars import get_special_chars


class SpecialCharsTest(TestCase):
    def check_chars(self, language, count, matches, *args, **kwargs):
        result = get_special_chars(language, *args, **kwargs)
        chars = {x[2] for x in result}
        self.assertEqual(len(chars), count)
        for match in matches:
            self.assertIn(match, chars)

    def test_af(self):
        chars = list(get_special_chars(Language(code="af")))
        self.assertEqual(len(chars), 11)

    def test_cs(self):
        chars = list(get_special_chars(Language(code="cs")))
        self.assertEqual(len(chars), 10)

    def test_brx(self):
        chars = list(get_special_chars(Language(code="brx")))
        self.assertEqual(len(chars), 10)

    def test_brx_add(self):
        chars = list(get_special_chars(Language(code="brx"), "ahoj"))
        self.assertEqual(len(chars), 14)

    @override_settings(SPECIAL_CHARS=[chr(x) for x in range(256)])
    def test_settings(self):
        chars = list(get_special_chars(Language(code="cs")))
        self.assertEqual(len(chars), 262)

    def test_additional(self):
        self.check_chars(
            Language(code="cs"), 14, ["a", "h", "o", "j"], additional="ahoj"
        )

    def test_arrows(self):
        self.check_chars(Language(code="cs"), 12, ["→", "⇒"], source="→⇒→⇒")

    def test_arrows_rtl(self):
        self.check_chars(
            Language(code="ar", direction="rtl"), 13, ["←", "⇐"], source="→⇒→⇒"
        )
