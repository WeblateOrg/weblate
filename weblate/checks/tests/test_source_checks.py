# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for source checks."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from weblate.checks.models import Check
from weblate.checks.source import (
    EllipsisCheck,
    LongUntranslatedCheck,
    MultipleFailingCheck,
    OptionalPluralCheck,
)
from weblate.checks.tests.test_checks import MockUnit
from weblate.trans.models import Unit
from weblate.trans.tests.test_views import FixtureTestCase


class OptionalPluralCheckTest(TestCase):
    def setUp(self) -> None:
        self.check = OptionalPluralCheck()

    def test_none(self) -> None:
        self.assertFalse(self.check.check_source(["text"], MockUnit()))

    def test_plural(self) -> None:
        self.assertFalse(self.check.check_source(["text", "texts"], MockUnit()))

    def test_failing(self) -> None:
        self.assertTrue(self.check.check_source(["text(s)"], MockUnit()))


class EllipsisCheckTest(TestCase):
    def setUp(self) -> None:
        self.check = EllipsisCheck()

    def test_none(self) -> None:
        self.assertFalse(self.check.check_source(["text"], MockUnit()))

    def test_good(self) -> None:
        self.assertFalse(self.check.check_source(["text…"], MockUnit()))

    def test_failing(self) -> None:
        self.assertTrue(self.check.check_source(["text..."], MockUnit()))


class LongUntranslatedCheckTestCase(FixtureTestCase):
    check = LongUntranslatedCheck()

    def test_recent(self) -> None:
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now()
        unit.save()
        unit.run_checks()
        self.assertNotIn("long_untranslated", unit.all_checks_names)

    def test_old(self) -> None:
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now() - timedelta(days=100)
        unit.save()
        unit.run_checks()
        self.assertNotIn("long_untranslated", unit.all_checks_names)

    def test_old_untranslated(self) -> None:
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now() - timedelta(days=100)
        unit.save()
        unit.translation.component.stats.set_data({"translated": 1, "all": 1})
        unit.translation.component.stats.save()
        unit.run_checks()
        self.assertIn("long_untranslated", unit.all_checks_names)

    def test_old_untranslated_batched(self) -> None:
        unit = self.get_unit(language="en")
        unit.timestamp = timezone.now() - timedelta(days=100)
        unit.save()
        unit.translation.component.stats.set_data({"translated": 1, "all": 1})
        unit.translation.component.stats.save()
        self.check.perform_batch(self.component)
        self.assertIn("long_untranslated", unit.all_checks_names)


class MultipleFailingCheckTestCase(FixtureTestCase):
    check = MultipleFailingCheck()

    def test_description(self) -> None:
        unit = self.get_unit(
            source="Try Weblate at <https://demo.weblate.org/>!\n", language="en"
        )
        check = Check(unit=unit)
        description = self.check.get_description(check)
        self.assertIn(
            "Following checks are failing:<dl><dt>Unchanged translation</dt>",
            description,
        )
        self.assertIn("Czech", description)
        self.assertIn("German", description)

    def test_multiple_failures(self) -> None:
        # Create multiple units with the same source to trigger the "same" check
        for unit in Unit.objects.filter(
            translation__component=self.component, source__startswith="Hello, world!\n"
        ):
            if not unit.is_source:
                self.edit_unit(
                    unit.source,
                    unit.source,
                    unit.translation.language.code,
                    True,
                    unit.translation,
                )
        source_unit = self.get_unit(language="en")
        child_unit = unit.unit_set.exclude(pk=source_unit.id).first()
        child_unit.run_checks()
        self.assertIn("same", child_unit.all_checks_names)
        source_unit.run_checks()
        self.assertTrue(self.check.check_source([], source_unit))

    def test_multiple_failures_batched(self) -> None:
        # Create multiple units with the same source to trigger the "same" check
        for unit in Unit.objects.filter(
            translation__component=self.component, source__startswith="Hello, world!\n"
        ):
            if not unit.is_source:
                self.edit_unit(
                    unit.source,
                    unit.source,
                    unit.translation.language.code,
                    True,
                    unit.translation,
                )
        source_unit = self.get_unit(language="en")
        child_unit = unit.unit_set.exclude(pk=source_unit.id).first()
        child_unit.run_checks()
        self.assertIn("same", child_unit.all_checks_names)
        self.check.perform_batch(self.component)
        self.assertTrue(self.check.check_source([], source_unit))
