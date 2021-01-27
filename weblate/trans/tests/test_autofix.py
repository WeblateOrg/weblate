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

"""Tests for automatix fixups."""

from django.test import TestCase

from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.autofixes import fix_target
from weblate.trans.autofixes.chars import (
    RemoveControlChars,
    RemoveZeroSpace,
    ReplaceTrailingDotsWithEllipsis,
)
from weblate.trans.autofixes.custom import DoubleApostrophes
from weblate.trans.autofixes.html import BleachHTML
from weblate.trans.autofixes.whitespace import SameBookendingWhitespace


class AutoFixTest(TestCase):
    def test_ellipsis(self):
        unit = MockUnit(source="Foo…")
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEqual(fix.fix_target(["Bar..."], unit), (["Bar…"], True))
        self.assertEqual(fix.fix_target(["Bar... "], unit), (["Bar... "], False))

    def test_no_ellipsis(self):
        unit = MockUnit(source="Foo...")
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEqual(fix.fix_target(["Bar..."], unit), (["Bar..."], False))
        self.assertEqual(fix.fix_target(["Bar…"], unit), (["Bar…"], False))

    def test_whitespace(self):
        unit = MockUnit(source="Foo\n")
        fix = SameBookendingWhitespace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar\n"], True))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar\n"], False))
        unit = MockUnit(source=" ")
        self.assertEqual(fix.fix_target(["  "], unit), (["  "], False))

    def test_no_whitespace(self):
        unit = MockUnit(source="Foo")
        fix = SameBookendingWhitespace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar"], True))

    def test_whitespace_flags(self):
        fix = SameBookendingWhitespace()
        unit = MockUnit(source="str", flags="ignore-begin-space")
        self.assertEqual(fix.fix_target(["  str"], unit), (["  str"], False))
        unit = MockUnit(source="str", flags="ignore-end-space")
        self.assertEqual(fix.fix_target(["  str  "], unit), (["str  "], True))

    def test_html(self):
        fix = BleachHTML()
        unit = MockUnit(source='<a href="script:foo()">link</a>', flags="safe-html")
        self.assertEqual(
            fix.fix_target(['<a href="script:foo()">link</a>'], unit),
            (["<a>link</a>"], True),
        )
        self.assertEqual(
            fix.fix_target(['<a href="#" onclick="foo()">link</a>'], unit),
            (['<a href="#">link</a>'], True),
        )

    def test_zerospace(self):
        unit = MockUnit(source="Foo\u200b")
        fix = RemoveZeroSpace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\u200b"], unit), (["Bar\u200b"], False))

    def test_no_zerospace(self):
        unit = MockUnit(source="Foo")
        fix = RemoveZeroSpace()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\u200b"], unit), (["Bar"], True))

    def test_controlchars(self):
        unit = MockUnit(source="Foo\x1b")
        fix = RemoveControlChars()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\x1b"], unit), (["Bar\x1b"], False))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar\n"], False))

    def test_no_controlchars(self):
        unit = MockUnit(source="Foo")
        fix = RemoveControlChars()
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        self.assertEqual(fix.fix_target(["Bar\x1b"], unit), (["Bar"], True))
        self.assertEqual(fix.fix_target(["Bar\n"], unit), (["Bar\n"], False))

    def test_fix_target(self):
        unit = MockUnit(source="Foo…")
        fixed, fixups = fix_target(["Bar..."], unit)
        self.assertEqual(fixed, ["Bar…"])
        self.assertEqual(len(fixups), 1)
        self.assertEqual(str(fixups[0]), "Trailing ellipsis")

    def test_apostrophes(self):
        unit = MockUnit(source="Foo")
        fix = DoubleApostrophes()
        # No flags
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        # No format string, but forced
        unit.flags = "java-messageformat"
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        # No format string
        unit.flags = "auto-java-messageformat"
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        unit.source = "test {0}"
        # Nothing to fix
        self.assertEqual(fix.fix_target(["r {0}"], unit), (["r {0}"], False))
        # Correct string
        self.assertEqual(fix.fix_target(["''r'' {0}"], unit), (["''r'' {0}"], False))
        # String with quoted format string
        self.assertEqual(
            fix.fix_target(["''r'' '{0}'"], unit), (["''r'' '{0}'"], False)
        )
        # Fixes
        self.assertEqual(fix.fix_target(["'r''' {0}"], unit), (["''r'' {0}"], True))
        # Fixes keeping double ones
        self.assertEqual(
            fix.fix_target(["'''''''r'''' {0}"], unit), (["''''r'''' {0}"], True)
        )
        # Quoted format
        self.assertEqual(fix.fix_target(["'r''' {0}"], unit), (["''r'' {0}"], True))
        unit.source = "foo"
        unit.flags = "java-messageformat"
        self.assertEqual(fix.fix_target(["bar'"], unit), (["bar''"], True))
