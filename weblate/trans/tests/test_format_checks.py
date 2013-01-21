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
Tests for quality checks.
"""

from django.test import TestCase
from weblate.trans.checks.format import (
    PythonFormatCheck, PHPFormatCheck, CFormatCheck,
)
from weblate.trans.tests.test_checks import Language, Unit


class PythonFormatCheckTest(TestCase):
    def setUp(self):
        self.check = PythonFormatCheck()

    def test_no_format(self):
        self.assertFalse(self.check.check_format(
            'strins',
            'string',
            Unit('python_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            Unit('python_format'),
            0,
            False
        ))

    def test_percent_format(self):
        self.assertFalse(self.check.check_format(
            u'%d%% string',
            u'%d%% string',
            Unit('python_percent_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s string',
            u'%(name)s string',
            Unit('python_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            Unit('python_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%(name)s string',
            u'string',
            Unit('python_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%(name)s string',
            u'string',
            Unit('python_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            Unit('python_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%(name)s string',
            u'%(jmeno)s string',
            Unit('python_wrong_named_format'),
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
            Unit('php_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            Unit('php_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%1$s string',
            u'%1$s string',
            Unit('php_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            Unit('php_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%1$s string',
            u'string',
            Unit('php_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%1$s string',
            u'string',
            Unit('php_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            Unit('php_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%1$s string',
            u'%s string',
            Unit('php_wrong_named_format'),
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
            Unit('c_no_format'),
            0,
            False
        ))

    def test_format(self):
        self.assertFalse(self.check.check_format(
            u'%s string',
            u'%s string',
            Unit('c_format'),
            0,
            False
        ))

    def test_named_format(self):
        self.assertFalse(self.check.check_format(
            u'%10s string',
            u'%10s string',
            Unit('c_named_format'),
            0,
            False
        ))

    def test_missing_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'string',
            Unit('c_missing_format'),
            0,
            False
        ))

    def test_missing_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%10s string',
            u'string',
            Unit('c_missing_named_format'),
            0,
            False
        ))

    def test_missing_named_format_ignore(self):
        self.assertFalse(self.check.check_format(
            u'%10s string',
            u'string',
            Unit('c_missing_named_format'),
            0,
            True
        ))

    def test_wrong_format(self):
        self.assertTrue(self.check.check_format(
            u'%s string',
            u'%c string',
            Unit('c_wrong_format'),
            0,
            False
        ))

    def test_wrong_named_format(self):
        self.assertTrue(self.check.check_format(
            u'%10s string',
            u'%20s string',
            Unit('c_wrong_named_format'),
            0,
            False
        ))
