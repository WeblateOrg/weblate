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
Tests for quality checks.
"""

from unittest import TestCase
from weblate.trans.checks.format import (
    PythonFormatCheck, PHPFormatCheck, CFormatCheck, PythonBraceFormatCheck,
)
from weblate.trans.tests.test_checks import MockUnit


class PythonFormatCheckTest(TestCase):
    def setUp(self):
        self.check = PythonFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            MockUnit('python_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            MockUnit('python_format'),
            0,
            False
        ))

    def test_percent_format(self):
        self.assertFalse(self.check.check_format(
            u'%d%% string',
            u'%d%% string',
            MockUnit('python_percent_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s string',
            u'%(name)s string',
            MockUnit('python_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            MockUnit('python_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%(name)s string',
            u'string',
            MockUnit('python_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s string',
            u'string',
            MockUnit('python_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            MockUnit('python_wrong_format'),
            0,
            False
        ))

    def test_reordered_format(self):
        self.assertTrue(self.check.check_format(
            u'%s %d string',
            u'%d %s string',
            MockUnit('python_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%(name)s string',
            u'%(jmeno)s string',
            MockUnit('python_wrong_named_format'),
            0,
            False
        ))

    def test_reordered_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s %(foo)s string',
            u'%(foo)s %(name)s string',
            MockUnit('python_reordered_named_format'),
            0,
            False
        ))

    def test_reordered_named_format_long(self):
        self.assertFalse(self.check.check_format(
            u'%(count)d strings into %(languages)d languages %(percent)d%%',
            u'%(languages)d dil içinde %(count)d satır %%%(percent)d',
            MockUnit('python_reordered_named_format_long'),
            0,
            False
        ))


class PHPFormatCheckTest(TestCase):
    def setUp(self):
        self.check = PHPFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            MockUnit('php_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            MockUnit('php_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%1$s string',
            u'%1$s string',
            MockUnit('php_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            MockUnit('php_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%1$s string',
            u'string',
            MockUnit('php_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%1$s string',
            u'string',
            MockUnit('php_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            MockUnit('php_wrong_format'),
            0,
            False
        ))

    def test_double_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%s%s string',
            MockUnit('php_double_format'),
            0,
            False
        ))

    def test_reorder_format(self):
        self.assertFalse(self.check.check_format(
            u'%1$s %2$s string',
            u'%2$s %1$s string',
            MockUnit('php_reorder_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%1$s string',
            u'%s string',
            MockUnit('php_wrong_named_format'),
            0,
            False
        ))

    def test_wrong_percent_format(self):
        self.assertTrue(self.check.check_format(
            u'%s%% (0.1%%)',
            u'%s%% (0.1%)',
            MockUnit('php_wrong_percent_format'),
            0,
            False
        ))

    def test_missing_percent_format(self):
        self.assertFalse(self.check.check_format(
            u'%s%% %%',
            u'%s%% percent',
            MockUnit('php_missing_percent_format'),
            0,
            False
        ))


class CFormatCheckTest(TestCase):
    def setUp(self):
        self.check = CFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            MockUnit('c_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            MockUnit('c_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%10s string',
            u'%10s string',
            MockUnit('c_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            MockUnit('c_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%10s string',
            u'string',
            MockUnit('c_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%10s string',
            u'string',
            MockUnit('c_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            MockUnit('c_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%10s string',
            u'%20s string',
            MockUnit('c_wrong_named_format'),
            0,
            False
        ))


class PythonBraceFormatCheckTest(TestCase):
    def setUp(self):
        self.check = PythonBraceFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            MockUnit('python_brace_no_format'),
            0,
            False
        ))

    def test_position_format(self):
        self.assertFalse(self.check.check_format(
            u'{} string {}',
            u'{} string {}',
            MockUnit('python_brace_position_format'),
            0,
            False
        ))

    def test_wrong_position_format(self):
        self.assertTrue(self.check.check_format(
            u'{} string',
            u'{} string {}',
            MockUnit('python_brace_wrong_position_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'{s1} string {s2}',
            u'{s1} string {s2}',
            MockUnit('python_brace_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'{} string',
            u'string',
            MockUnit('python_brace_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'{s1} string',
            u'string',
            MockUnit('python_brace_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'{s} string',
            u'string',
            MockUnit('python_brace_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'{s} string',
            u'{c} string',
            MockUnit('python_brace_wrong_format'),
            0,
            False
        ))

    def test_escaping(self):
        self.assertFalse(self.check.check_format(
            u'{{ string }}',
            u'string',
            MockUnit('python_brace_escaping'),
            0,
            False
        ))

    def test_attribute_format(self):
        self.assertFalse(self.check.check_format(
            u'{s.foo} string',
            u'{s.foo} string',
            MockUnit('python_brace_attribute_format'),
            0,
            False
        ))

    def test_wrong_attribute_format(self):
        self.assertTrue(self.check.check_format(
            u'{s.foo} string',
            u'{s.bar} string',
            MockUnit('python_brace_wrong_attribute_format'),
            0,
            False
        ))
