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
from weblate.trans.checks.consistency import (
    SameCheck,
    PluralsCheck,
)
from weblate.trans.tests.test_checks import Language


class SameCheckTest(TestCase):
    def setUp(self):
        self.check = SameCheck()

    def test_not_same(self):
        self.assertFalse(self.check.check_single(
            'source',
            'translation',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_same(self):
        self.assertTrue(self.check.check_single(
            'source',
            'source',
            '',
            Language('cs'),
            None,
            0
        ))

    def test_same_english(self):
        self.assertFalse(self.check.check_single(
            'source',
            'source',
            '',
            Language('en'),
            None,
            0
        ))

    def test_same_format(self):
        self.assertFalse(self.check.check_single(
            '%(source)s',
            '%(source)s',
            'python-format',
            Language('cs'),
            None,
            0
        ))


class PluralsCheckTest(TestCase):
    def setUp(self):
        self.check = PluralsCheck()

    def test_none(self):
        self.assertFalse(self.check.check(
            ['string'],
            ['string'],
            '',
            Language('cs'),
            None
        ))

    def test_empty(self):
        self.assertFalse(self.check.check(
            ['string', 'plural'],
            ['', ''],
            '',
            Language('cs'),
            None
        ))

    def test_partial_empty(self):
        self.assertTrue(self.check.check(
            ['string', 'plural'],
            ['string', ''],
            '',
            Language('cs'),
            None
        ))
