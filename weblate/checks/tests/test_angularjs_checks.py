# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
# Copyright © 2015 Philipp Wolfer <ph.wolfer@gmail.com>
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

"""
Tests for AngularJS checks.
"""

from unittest import TestCase
from weblate.checks.angularjs import AngularJSInterpolationCheck
from weblate.checks.tests.test_checks import MockUnit


class AngularJSInterpolationCheckTest(TestCase):
    def setUp(self):
        self.check = AngularJSInterpolationCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_single(
            'strins',
            'string',
            MockUnit('angularjs_no_format', flags='angularjs-format')
        ))

    def test_format(self):
        self.assertFalse(self.check.check_single(
            u'{{name}} string {{other}}',
            u'{{name}} {{other}} string',
            MockUnit('angularjs_format', flags='angularjs-format')
        ))

    def test_format_ignore_position(self):
        self.assertFalse(self.check.check_single(
            u'{{name}} string {{other}}',
            u'{{other}} string {{name}}',
            MockUnit('angularjs_format_ignore_position',
                     flags='angularjs-format')
        ))

    def test_different_whitespace(self):
        self.assertFalse(self.check.check_single(
            u'{{ name   }} string',
            u'{{name}} string',
            MockUnit('angularjs_different_whitespace',
                     flags='angularjs-format')
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_single(
            u'{{name}} string',
            u'string',
            MockUnit('angularjs_missing_format', flags='angularjs-format')
        ))

    def test_wrong_value(self):
        self.assertTrue(self.check.check_single(
            u'{{name}} string',
            u'{{nameerror}} string',
            MockUnit('angularjs_wrong_value', flags='angularjs-format')
        ))

    def test_extended_formatting(self):
        self.assertFalse(self.check.check_single(
            u'Value: {{ something.value | currency }}',
            u'Wert: {{ something.value | currency }}',
            MockUnit('angularjs_format', flags='angularjs-format')
        ))
        self.assertTrue(self.check.check_single(
            u'Value: {{ something.value | currency }}',
            u'Value: {{ something.value }}',
            MockUnit('angularjs_format', flags='angularjs-format')
        ))

    def test_check_highlight(self):
        highlights = self.check.check_highlight(
            u'{{name}} {{ something.value | currency }} string',
            MockUnit('angularjs_format', flags='angularjs-format'))
        self.assertEqual(2, len(highlights))
        self.assertEqual(0, highlights[0][0])
        self.assertEqual(8, highlights[0][1])
        self.assertEqual(9, highlights[1][0])
        self.assertEqual(41, highlights[1][1])

    def test_check_highlight_ignored(self):
        highlights = self.check.check_highlight(
            u'{{name}} {{other}} string',
            MockUnit('angularjs_format', flags='ignore-angularjs-format'))
        self.assertEqual([], highlights)
