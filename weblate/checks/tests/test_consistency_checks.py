# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
Tests for quality checks.
"""

from django.test import TestCase
from weblate.checks.consistency import (
    PluralsCheck, SamePluralsCheck, TranslatedCheck,
)
from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.tests.test_views import ViewTestCase


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

    def test_hit(self):
        self.assertTrue(self.check.check_target(
            ['string', 'plural'],
            ['string', ''],
            MockUnit('plural_partial_empty'),
        ))

    def test_good(self):
        self.assertFalse(self.check.check_target(
            ['string', 'plural'],
            ['translation', 'trplural'],
            MockUnit('plural_good'),
        ))


class SamePluralsCheckTest(PluralsCheckTest):
    def setUp(self):
        self.check = SamePluralsCheck()

    def test_hit(self):
        self.assertTrue(self.check.check_target(
            ['string', 'plural'],
            ['string', 'string'],
            MockUnit('plural_partial_empty'),
        ))


class TranslatedCheckTest(ViewTestCase):
    def setUp(self):
        super(TranslatedCheckTest, self).setUp()
        self.check = TranslatedCheck()

    def run_check(self):
        unit = self.get_unit()
        return self.check.check_target(
            unit.get_source_plurals(),
            unit.get_target_plurals(),
            unit
        )

    def test_none(self):
        self.assertFalse(self.run_check())

    def test_translated(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        self.assertFalse(self.run_check())

    def test_untranslated(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        self.edit_unit(
            'Hello, world!\n',
            ''
        )
        self.assertTrue(self.run_check())
