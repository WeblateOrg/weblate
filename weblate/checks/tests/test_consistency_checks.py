# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for consistency checks."""

from django.test import TestCase

from weblate.checks.consistency import PluralsCheck, SamePluralsCheck, TranslatedCheck
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.models import Change
from weblate.trans.tests.test_views import ViewTestCase


class PluralsCheckTest(TestCase):
    def setUp(self):
        self.check = PluralsCheck()

    def test_none(self):
        self.assertFalse(
            self.check.check_target(["string"], ["string"], MockUnit("plural_none"))
        )

    def test_empty(self):
        self.assertFalse(
            self.check.check_target(
                ["string", "plural"], ["", ""], MockUnit("plural_empty")
            )
        )

    def test_hit(self):
        self.assertTrue(
            self.check.check_target(
                ["string", "plural"], ["string", ""], MockUnit("plural_partial_empty")
            )
        )

    def test_good(self):
        self.assertFalse(
            self.check.check_target(
                ["string", "plural"],
                ["translation", "trplural"],
                MockUnit("plural_good"),
            )
        )


class SamePluralsCheckTest(PluralsCheckTest):
    def setUp(self):
        self.check = SamePluralsCheck()

    def test_hit(self):
        self.assertTrue(
            self.check.check_target(
                ["string", "plural"],
                ["string", "string"],
                MockUnit("plural_partial_empty"),
            )
        )


class TranslatedCheckTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.check = TranslatedCheck()

    def run_check(self):
        unit = self.get_unit()
        return self.check.check_target(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        )

    def test_none(self):
        self.assertFalse(self.run_check())

    def test_translated(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.assertFalse(self.run_check())

    def test_untranslated(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "")
        self.assertTrue(self.run_check())

    def test_source_change(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "")
        unit = self.get_unit()
        unit.change_set.create(action=Change.ACTION_SOURCE_CHANGE)
        self.assertFalse(self.run_check())

    def test_get_description(self):
        self.test_untranslated()
        check = Check(unit=self.get_unit())
        self.assertEqual(
            self.check.get_description(check),
            'Previous translation was "Nazdar svete!\n".',
        )
