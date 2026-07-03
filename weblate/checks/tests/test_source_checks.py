# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for source checks."""

from datetime import timedelta
from typing import cast

from django.test import TestCase
from django.utils import timezone

from weblate.checks.models import Check
from weblate.checks.source import (
    EllipsisCheck,
    LongUntranslatedCheck,
    MultipleFailingCheck,
    OptionalPluralCheck,
    SourceMaxLengthCheck,
)
from weblate.trans.models import Unit
from weblate.trans.tests.factories import make_language, make_unit
from weblate.trans.tests.test_views import FixtureComponentTestCase, FixtureTestCase
from weblate.utils.state import STATE_EMPTY, STATE_TRANSLATED


class OptionalPluralCheckTest(TestCase):
    def setUp(self) -> None:
        self.check = OptionalPluralCheck()

    def test_none(self) -> None:
        self.assertFalse(self.check.check_source(["text"], make_unit()))

    def test_plural(self) -> None:
        self.assertFalse(self.check.check_source(["text", "texts"], make_unit()))

    def test_failing(self) -> None:
        self.assertTrue(self.check.check_source(["text(s)"], make_unit()))


class EllipsisCheckTest(TestCase):
    def setUp(self) -> None:
        self.check = EllipsisCheck()

    def test_none(self) -> None:
        self.assertFalse(self.check.check_source(["text"], make_unit()))

    def test_good(self) -> None:
        self.assertFalse(self.check.check_source(["text…"], make_unit()))

    def test_failing(self) -> None:
        self.assertTrue(self.check.check_source(["text..."], make_unit()))


class SourceMaxLengthCheckTest(TestCase):
    def setUp(self) -> None:
        self.check = SourceMaxLengthCheck()

    def get_unit(self, flags: str, source_language: str = "en") -> Unit:
        unit = make_unit(flags=flags, is_source=True)
        language = make_language(source_language)
        unit.translation.language = language
        unit.translation.language_code = language.code
        unit.translation.component.source_language = language
        return unit

    def test_no_flag(self) -> None:
        self.assertFalse(self.check.check_source(["x" * 200], self.get_unit("")))

    def test_english_allows_fifteen_percent_headroom(self) -> None:
        unit = self.get_unit("max-length:100")

        self.assertFalse(self.check.check_source(["x" * 85], unit))
        self.assertTrue(self.check.check_source(["x" * 86], unit))

    def test_english_variant_uses_headroom(self) -> None:
        unit = self.get_unit("max-length:100", "en_US")

        self.assertFalse(self.check.check_source(["x" * 85], unit))
        self.assertTrue(self.check.check_source(["x" * 86], unit))

    def test_non_english_uses_max_length(self) -> None:
        unit = self.get_unit("max-length:100", "cs")

        self.assertFalse(self.check.check_source(["x" * 100], unit))
        self.assertTrue(self.check.check_source(["x" * 101], unit))

    def test_invalid_flag(self) -> None:
        self.assertTrue(
            self.check.check_source(["text"], self.get_unit("max-length:*"))
        )

    def test_ignored(self) -> None:
        unit = self.get_unit("max-length:100, ignore-source-max-length")

        self.assertFalse(self.check.check_source(["x" * 86], unit))

    def test_plural(self) -> None:
        unit = self.get_unit("max-length:100")

        self.assertFalse(self.check.check_source(["x" * 84, "x" * 85], unit))
        self.assertTrue(self.check.check_source(["x" * 84, "x" * 86], unit))

    def test_replacements(self) -> None:
        unit = self.get_unit('max-length:100, replacements:%s:"very long text"')

        self.assertFalse(self.check.check_source(["x" * 82], unit))
        self.assertTrue(self.check.check_source(["x" * 82 + "%s"], unit))

    def test_invalid_replacements(self) -> None:
        unit = self.get_unit("max-length:100, replacements:%s")

        self.assertFalse(self.check.check_source(["x" * 85], unit))
        self.assertTrue(self.check.check_source(["x" * 86], unit))

    def test_xml_text(self) -> None:
        unit = self.get_unit("max-length:100, xml-text")

        self.assertFalse(self.check.check_source([f"<mrk>{'x' * 85}</mrk>"], unit))
        self.assertTrue(self.check.check_source([f"<mrk>{'x' * 86}</mrk>"], unit))


class LongUntranslatedCheckTestCase(FixtureComponentTestCase):
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
        Unit.objects.filter(translation__component=unit.translation.component).exclude(
            source_unit=unit
        ).update(state=STATE_TRANSLATED)
        unit.unit_set.exclude(pk=unit.pk).update(state=STATE_EMPTY, target="")
        self.check.perform_batch(self.component)
        unit = Unit.objects.get(pk=unit.pk)
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
        child_unit = source_unit.unit_set.exclude(pk=source_unit.id).first()
        self.assertIsNotNone(child_unit)
        checked_child_unit = cast("Unit", child_unit)
        checked_child_unit.run_checks()
        self.assertIn("same", checked_child_unit.all_checks_names)
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
        child_unit = source_unit.unit_set.exclude(pk=source_unit.id).first()
        self.assertIsNotNone(child_unit)
        checked_child_unit = cast("Unit", child_unit)
        checked_child_unit.run_checks()
        self.assertIn("same", checked_child_unit.all_checks_names)
        self.check.perform_batch(self.component)
        self.assertTrue(self.check.check_source([], source_unit))
