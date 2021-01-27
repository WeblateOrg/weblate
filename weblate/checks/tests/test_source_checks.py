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

"""Tests for source checks."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from weblate.checks.source import (
    EllipsisCheck,
    LongUntranslatedCheck,
    OptionalPluralCheck,
)
from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.tests.test_views import FixtureTestCase


class OptionalPluralCheckTest(TestCase):
    def setUp(self):
        self.check = OptionalPluralCheck()

    def test_none(self):
        self.assertFalse(self.check.check_source(["text"], MockUnit()))

    def test_plural(self):
        self.assertFalse(self.check.check_source(["text", "texts"], MockUnit()))

    def test_failing(self):
        self.assertTrue(self.check.check_source(["text(s)"], MockUnit()))


class EllipsisCheckTest(TestCase):
    def setUp(self):
        self.check = EllipsisCheck()

    def test_none(self):
        self.assertFalse(self.check.check_source(["text"], MockUnit()))

    def test_good(self):
        self.assertFalse(self.check.check_source(["text…"], MockUnit()))

    def test_failing(self):
        self.assertTrue(self.check.check_source(["text..."], MockUnit()))


class LongUntranslatedCheckTestCase(FixtureTestCase):
    check = LongUntranslatedCheck()

    def test_recent(self):
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now()
        unit.run_checks()
        self.assertNotIn("long_untranslated", unit.all_checks_names)

    def test_old(self):
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now() - timedelta(days=100)
        unit.run_checks()
        self.assertNotIn("long_untranslated", unit.all_checks_names)

    def test_old_untranslated(self):
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now() - timedelta(days=100)
        unit.translation.component.stats.lazy_translated_percent = 100
        unit.run_checks()
        self.assertIn("long_untranslated", unit.all_checks_names)
