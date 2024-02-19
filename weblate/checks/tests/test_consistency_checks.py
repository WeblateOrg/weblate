# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for consistency checks."""

from django.test import TestCase

from weblate.checks.consistency import (
    ConsistencyCheck,
    PluralsCheck,
    ReusedCheck,
    SamePluralsCheck,
    TranslatedCheck,
)
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.models import Change
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


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


class ConsistencyCheckTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.other = self.create_link_existing()
        self.translation_1 = self.component.translation_set.get(language__code="cs")
        self.translation_2 = self.other.translation_set.get(language__code="cs")
        self._id_hash = 1000

    def add_unit(
        self,
        translation,
        context: str,
        source: str,
        target: str,
        increment: bool = True,
    ):
        if increment:
            self._id_hash += 1
        source_unit = translation.component.source_translation.unit_set.create(
            id_hash=self._id_hash,
            position=self._id_hash,
            context=context,
            source=source,
            target=source,
            state=STATE_TRANSLATED,
        )
        return translation.unit_set.create(
            id_hash=self._id_hash,
            position=self._id_hash,
            source_unit=source_unit,
            context=context,
            source=source,
            target=target,
            state=STATE_TRANSLATED,
        )

    def test_reuse(self):
        check = ReusedCheck()
        self.assertEqual(check.check_component(self.component), [])

        # Add non-triggering units
        unit = self.add_unit(self.translation_1, "one", "One", "Jeden")
        unit = self.add_unit(self.translation_2, "one", "One", "Jeden", increment=False)
        self.assertFalse(check.check_target_unit([], [], unit))
        self.assertEqual(check.check_component(self.component), [])

        # Add triggering unit
        unit2 = self.add_unit(self.translation_2, "two", "Two", "Jeden")
        self.assertTrue(check.check_target_unit([], [], unit2))
        # Add another triggering unit
        unit3 = self.add_unit(self.translation_2, "three", "Three", "Jeden")
        self.assertTrue(check.check_target_unit([], [], unit3))

        self.assertNotEqual(check.check_component(self.component), [])

        # Run all checks
        unit2.run_checks()
        # All four units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 4)

        # Change translation
        unit2.translate(self.user, "Dva", STATE_TRANSLATED)
        # Some units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 3)
        # Change translation
        unit3.translate(self.user, "Tři", STATE_TRANSLATED)
        # No units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 0)

    def test_reuse_nocontext(self):
        check = ReusedCheck()
        self.assertEqual(check.check_component(self.component), [])

        # Add non-triggering units
        unit = self.add_unit(self.translation_1, "", "One", "Jeden")
        unit = self.add_unit(self.translation_2, "", "One", "Jeden", increment=False)
        self.assertFalse(check.check_target_unit([], [], unit))
        self.assertEqual(check.check_component(self.component), [])

        # Add triggering unit
        unit = self.add_unit(self.translation_2, "", "Two", "Jeden")
        self.assertTrue(check.check_target_unit([], [], unit))

        self.assertNotEqual(check.check_component(self.component), [])

    def test_consistency(self):
        check = ConsistencyCheck()
        self.assertEqual(check.check_component(self.component), [])

        # Add triggering units
        unit = self.add_unit(self.translation_1, "one", "One", "Jeden")
        self.assertFalse(check.check_target_unit([], [], unit))
        unit = self.add_unit(self.translation_2, "one", "One", "Jedna", increment=False)
        self.assertTrue(check.check_target_unit([], [], unit))

        self.assertNotEqual(check.check_component(self.component), [])
