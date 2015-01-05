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

from django.test import TestCase
from weblate.trans.checks.consistency import (
    PluralsCheck,
)
from weblate.trans.tests.test_checks import MockUnit


class PluralsCheckTest(TestCase):
    def setUp(self):
        self.check = PluralsCheck()

    def test_none(self):
        self.assertFalse(self.check.check_target(
            ['string'],
            ['string'],
            MockUnit('plural_none'),
        ))

    def test_empty(self):
        self.assertFalse(self.check.check_target(
            ['string', 'plural'],
            ['', ''],
            MockUnit('plural_empty'),
        ))

    def test_partial_empty(self):
        self.assertTrue(self.check.check_target(
            ['string', 'plural'],
            ['string', ''],
            MockUnit('plural_partial_empty'),
        ))
