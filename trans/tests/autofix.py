# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from trans.models.unit import Unit
from trans.autofixes.chars import ReplaceTrailingDotsWithEllipsis
from trans.autofixes.whitespace import SameBookendingWhitespace


class AutoFixTest(TestCase):
    def test_ellipsis(self):
        unit = Unit(source=u'Foo…')
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEquals(
            fix.fix_target(['Bar...'], unit),
            [u'Bar…']
        )
        self.assertEquals(
            fix.fix_target(['Bar... '], unit),
            [u'Bar... ']
        )

    def test_no_ellipsis(self):
        unit = Unit(source=u'Foo...')
        fix = ReplaceTrailingDotsWithEllipsis()
        self.assertEquals(
            fix.fix_target(['Bar...'], unit),
            [u'Bar...']
        )
        self.assertEquals(
            fix.fix_target([u'Bar…'], unit),
            [u'Bar…']
        )

    def test_whitespace(self):
        unit = Unit(source=u'Foo\n')
        fix = SameBookendingWhitespace()
        self.assertEquals(
            fix.fix_target(['Bar'], unit),
            [u'Bar\n']
        )
        self.assertEquals(
            fix.fix_target(['Bar\n'], unit),
            [u'Bar\n']
        )

    def test_no_whitespace(self):
        unit = Unit(source=u'Foo')
        fix = SameBookendingWhitespace()
        self.assertEquals(
            fix.fix_target(['Bar'], unit),
            [u'Bar']
        )
        self.assertEquals(
            fix.fix_target(['Bar\n'], unit),
            [u'Bar']
        )
