# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for automatix fixups.
"""

from django.test import TestCase
from weblate.trans.tests.test_checks import MockUnit
from weblate.trans.autofixes import fix_target
from weblate.trans.autofixes.chars import (
    ReplaceTrailingDotsWithEllipsis, RemoveZeroSpace,
)
from weblate.trans.autofixes.whitespace import SameBookendingWhitespace


class AutoFixTest(TestCase):
    def test_ellipsis(self):
        unit = MockUnit(source=u'Foo…')
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEqual(
            fix.fix_target(['Bar...'], unit),
            ([u'Bar…'], True)
        )
        self.assertEqual(
            fix.fix_target(['Bar... '], unit),
            ([u'Bar... '], False)
        )

    def test_no_ellipsis(self):
        unit = MockUnit(source=u'Foo...')
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEqual(
            fix.fix_target(['Bar...'], unit),
            ([u'Bar...'], False)
        )
        self.assertEqual(
            fix.fix_target([u'Bar…'], unit),
            ([u'Bar…'], False)
        )

    def test_whitespace(self):
        unit = MockUnit(source=u'Foo\n')
        fix = SameBookendingWhitespace()
        self.assertEqual(
            fix.fix_target(['Bar'], unit),
            ([u'Bar\n'], True)
        )
        self.assertEqual(
            fix.fix_target(['Bar\n'], unit),
            ([u'Bar\n'], False)
        )
        unit = MockUnit(source=u' ')
        self.assertEqual(
            fix.fix_target(['  '], unit),
            (['  '], False)
        )

    def test_no_whitespace(self):
        unit = MockUnit(source=u'Foo')
        fix = SameBookendingWhitespace()
        self.assertEqual(
            fix.fix_target(['Bar'], unit),
            ([u'Bar'], False)
        )
        self.assertEqual(
            fix.fix_target(['Bar\n'], unit),
            ([u'Bar'], True)
        )

    def test_zerospace(self):
        unit = MockUnit(source=u'Foo\u200b')
        fix = RemoveZeroSpace()
        self.assertEqual(
            fix.fix_target(['Bar'], unit),
            ([u'Bar'], False)
        )
        self.assertEqual(
            fix.fix_target([u'Bar\u200b'], unit),
            ([u'Bar\u200b'], False)
        )

    def test_no_zerospace(self):
        unit = MockUnit(source=u'Foo')
        fix = RemoveZeroSpace()
        self.assertEqual(
            fix.fix_target(['Bar'], unit),
            ([u'Bar'], False)
        )
        self.assertEqual(
            fix.fix_target([u'Bar\u200b'], unit),
            ([u'Bar'], True)
        )

    def test_fix_target(self):
        unit = MockUnit(source=u'Foo…')
        fixed, fixups = fix_target(['Bar...'], unit)
        self.assertEqual(fixed, [u'Bar…'])
        self.assertEqual(len(fixups), 1)
        self.assertEqual(unicode(fixups[0]), u'Trailing ellipsis')
