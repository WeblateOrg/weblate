# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for automatix fixups."""

from django.test import TestCase

from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.autofixes import fix_target
from weblate.trans.autofixes.chars import (
    DevanagariDanda,
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
        self.assertEqual(
            fix.fix_target(["<https://weblate.org>"], unit),
            ([""], True),
        )

    def test_html_markdown(self):
        fix = BleachHTML()
        unit = MockUnit(
            source='<a href="script:foo()">link</a>', flags="safe-html,md-text"
        )
        self.assertEqual(
            fix.fix_target(
                ['<a href="script:foo()">link</a><https://weblate.org>'], unit
            ),
            (["<a>link</a><https://weblate.org>"], True),
        )
        self.assertEqual(
            fix.fix_target(["<https://weblate.org>"], unit),
            (["<https://weblate.org>"], False),
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
        self.assertEqual(fix.fix_target(["Bar\x1b"], unit), (["Bar"], True))
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
        unit.flags = "java-format"
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        # No format string
        unit.flags = "auto-java-messageformat"
        self.assertEqual(fix.fix_target(["Bar"], unit), (["Bar"], False))
        unit.source = "test {0}"
        unit.sources = [unit.source]
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
        unit.sources = [unit.source]
        unit.flags = "java-format"
        self.assertEqual(fix.fix_target(["bar'"], unit), (["bar''"], True))

    def test_devanagaridanda(self):
        non_unit = MockUnit(source="Foo", code="bn")
        bn_unit = MockUnit(source="Foo.", code="bn")
        cs_unit = MockUnit(source="Foo.", code="cs")
        fix = DevanagariDanda()
        self.assertEqual(fix.fix_target(["Bar."], non_unit), (["Bar."], False))
        self.assertEqual(fix.fix_target(["Bar."], bn_unit), (["Bar।"], True))
        self.assertEqual(fix.fix_target(["Bar|"], bn_unit), (["Bar।"], True))
        self.assertEqual(fix.fix_target(["Bar।"], bn_unit), (["Bar।"], False))
        self.assertEqual(fix.fix_target(["Bar."], cs_unit), (["Bar."], False))
