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
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class PluralsCheckTest(TestCase):
    def setUp(self) -> None:
        self.check = PluralsCheck()

    def test_none(self) -> None:
        self.assertFalse(
            self.check.check_target(["string"], ["string"], MockUnit("plural_none"))
        )

    def test_empty(self) -> None:
        self.assertFalse(
            self.check.check_target(
                ["string", "plural"], ["", ""], MockUnit("plural_empty")
            )
        )

    def test_hit(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["string", "plural"], ["string", ""], MockUnit("plural_partial_empty")
            )
        )

    def test_good(self) -> None:
        self.assertFalse(
            self.check.check_target(
                ["string", "plural"],
                ["translation", "trplural"],
                MockUnit("plural_good"),
            )
        )


class SamePluralsCheckTest(PluralsCheckTest):
    def setUp(self) -> None:
        self.check = SamePluralsCheck()

    def test_hit(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["string", "plural"],
                ["string", "string"],
                MockUnit("plural_partial_empty"),
            )
        )


class TranslatedCheckTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.check = TranslatedCheck()

    def run_check(self):
        unit = self.get_unit()
        return self.check.check_target(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        )

    def test_none(self) -> None:
        self.assertFalse(self.run_check())

    def test_translated(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.assertFalse(self.run_check())

    def test_untranslated(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "")
        self.assertTrue(self.run_check())

    def test_source_change(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "")
        unit = self.get_unit()
        unit.change_set.create(action=ActionEvents.SOURCE_CHANGE)
        self.assertFalse(self.run_check())

    def test_get_description(self) -> None:
        self.test_untranslated()
        check = Check(unit=self.get_unit())
        self.assertEqual(
            self.check.get_description(check),
            'Previous translation was "Nazdar svete!\n".',
        )


class ConsistencyCheckTest(ViewTestCase):
    def setUp(self) -> None:
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

    def test_reuse(self) -> None:
        check = ReusedCheck()
        self.assertEqual(list(check.check_component(self.component)), [])

        # Add non-triggering units
        unit = self.add_unit(self.translation_1, "one", "One", "Jeden")
        unit = self.add_unit(self.translation_2, "one", "One", "Jeden", increment=False)
        self.assertFalse(check.check_target_unit([], [], unit))
        self.assertEqual(list(check.check_component(self.component)), [])

        # Add triggering unit
        unit2 = self.add_unit(self.translation_2, "two", "Two", "Jeden")
        self.assertTrue(check.check_target_unit([], [], unit2))
        # Add another triggering unit
        unit3 = self.add_unit(self.translation_2, "three", "Three", "Jeden")
        self.assertTrue(check.check_target_unit([], [], unit3))

        self.assertNotEqual(list(check.check_component(self.component)), [])

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

    def test_reuse_existing(self) -> None:
        check = ReusedCheck()
        self.assertEqual(list(check.check_component(self.component)), [])

        # Add units
        unit = self.add_unit(self.translation_1, "one", "One", "Dva")
        unit2 = self.add_unit(self.translation_2, "two", "Two", "")
        # Run all checks
        unit2.run_checks()
        # No units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 0)

        # Change translation
        Unit.objects.get(pk=unit2.pk).translate(self.user, "Dva", STATE_TRANSLATED)
        # Both units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 2)
        # Change translation
        Unit.objects.get(pk=unit.pk).translate(self.user, "Jeden", STATE_TRANSLATED)
        # No units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 0)

    def test_reuse_nocontext(self) -> None:
        check = ReusedCheck()
        self.assertEqual(list(check.check_component(self.component)), [])

        # Add non-triggering units
        unit = self.add_unit(self.translation_1, "", "One", "Jeden")
        unit = self.add_unit(self.translation_2, "", "One", "Jeden", increment=False)
        self.assertFalse(check.check_target_unit([], [], unit))
        self.assertEqual(list(check.check_component(self.component)), [])

        # Add triggering unit
        unit = self.add_unit(self.translation_2, "", "Two", "Jeden")
        self.assertTrue(check.check_target_unit([], [], unit))

        self.assertNotEqual(list(check.check_component(self.component)), [])

    def test_reuse_case(self) -> None:
        check = ReusedCheck()
        self.assertEqual(list(check.check_component(self.component)), [])
        self.translation_1.language = Language.objects.get(code="he")
        self.translation_1.save()
        self.translation_2.language = Language.objects.get(code="he")
        self.translation_2.save()

        # Add non-triggering units
        unit = self.add_unit(self.translation_1, "", "One", "Jeden")
        unit2 = self.add_unit(self.translation_2, "", "one", "Jeden")
        self.assertFalse(check.check_target_unit([], [], unit))
        # Verify there are no checks triggered
        self.assertEqual(list(check.check_component(self.component)), [])

        # Run all checks
        unit2.run_checks()
        self.assertEqual(Check.objects.filter(name="reused").count(), 0)

    def test_consistency(self) -> None:
        check = ConsistencyCheck()
        self.assertEqual(check.check_component(self.component), [])

        # Add triggering units
        unit = self.add_unit(self.translation_1, "one", "One", "Jeden")
        self.assertFalse(check.check_target_unit([], [], unit))
        unit = self.add_unit(self.translation_2, "one", "One", "Jedna", increment=False)
        self.assertTrue(check.check_target_unit([], [], unit))

        self.assertNotEqual(check.check_component(self.component), [])
