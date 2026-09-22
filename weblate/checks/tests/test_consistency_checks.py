# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for consistency checks."""

from __future__ import annotations

from unittest.mock import patch

from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from weblate.checks.base import TargetCheck
from weblate.checks.consistency import (
    ConsistencyCheck,
    PluralsCheck,
    ReusedCheck,
    SamePluralsCheck,
    TranslatedCheck,
)
from weblate.checks.models import CHECKS, Check
from weblate.checks.tasks import refresh_propagated_checks, schedule_propagated_checks
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Translation, Unit
from weblate.trans.tests.factories import make_unit
from weblate.trans.tests.test_views import (
    ComponentTestCase,
    FixtureTestCase,
)
from weblate.trans.util import join_plural
from weblate.utils.state import STATE_EMPTY, STATE_NEEDS_REWRITING, STATE_TRANSLATED


class PluralsCheckTest(TestCase):
    def setUp(self) -> None:
        self.check: PluralsCheck | SamePluralsCheck = PluralsCheck()

    def test_none(self) -> None:
        self.assertFalse(
            self.check.check_target(["string"], ["string"], make_unit("plural_none"))
        )

    def test_empty(self) -> None:
        self.assertFalse(
            self.check.check_target(
                ["string", "plural"], ["", ""], make_unit("plural_empty")
            )
        )

    def test_hit(self) -> None:
        self.assertTrue(
            self.check.check_target(
                ["string", "plural"], ["string", ""], make_unit("plural_partial_empty")
            )
        )

    def test_good(self) -> None:
        self.assertFalse(
            self.check.check_target(
                ["string", "plural"],
                ["translation", "trplural"],
                make_unit("plural_good"),
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
                make_unit("plural_partial_empty"),
            )
        )


class TranslatedCheckTest(FixtureTestCase):
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

    def test_run_checks_untranslated(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "")
        unit = self.get_unit()
        Check.objects.filter(unit=unit).delete()
        unit.clear_checks_cache()

        unit.run_checks()

        self.assertEqual(unit.state, STATE_EMPTY)
        self.assertIn("translated", unit.all_checks_names)

    def test_run_checks_untranslated_removes_stale_check(self) -> None:
        unit = self.get_unit()
        self.assertEqual(unit.state, STATE_EMPTY)
        Check.objects.create(unit=unit, name="same")

        unit.run_checks()

        self.assertNotIn("same", unit.all_checks_names)


class ReusedCheckGuardTest(SimpleTestCase):
    def test_reuse_ignores_non_propagating_component(self) -> None:
        check = ReusedCheck()
        unit = make_unit(target="Jeden")
        unit.translation.component.allow_translation_propagation = False
        unit.translation.component.batch_checks = True

        with patch.object(check, "handle_batch") as handle_batch:
            self.assertFalse(check.check_target_unit([], [], unit))

        handle_batch.assert_not_called()


class ConsistencyCheckTest(ComponentTestCase):
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

        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
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
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            unit2.translate(self.user, "Dva", STATE_TRANSLATED)
        # Some units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 3)
        # Change translation
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
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
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            unit2.run_checks()
        # No units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 0)

        # Change translation
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            Unit.objects.get(pk=unit2.pk).translate(self.user, "Dva", STATE_TRANSLATED)
        # Both units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 2)
        # Change translation
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            Unit.objects.get(pk=unit.pk).translate(self.user, "Jeden", STATE_TRANSLATED)
        # No units should be now failing
        self.assertEqual(Check.objects.filter(name="reused").count(), 0)

    def test_reuse_updates_related_checks_after_commit(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        edited = self.add_unit(self.translation_1, "two", "Two", "")
        Check.objects.filter(unit__in=[first, edited]).delete()
        edited = Unit.objects.get(pk=edited.pk)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            edited.translate(self.user, "Shared", STATE_TRANSLATED)
            self.assertTrue(Check.objects.filter(unit=edited, name="reused").exists())
            self.assertFalse(Check.objects.filter(unit=first, name="reused").exists())
        self.assertTrue(Check.objects.filter(unit=first, name="reused").exists())

    def test_first_translation_skips_empty_target_group(self) -> None:
        for target in ("", join_plural(["", ""])):
            with self.subTest(target=target):
                unit = self.add_unit(self.translation_1, "empty", "Empty", target)
                Unit.objects.filter(pk=unit.pk).update(state=STATE_EMPTY)
                with (
                    patch(
                        "weblate.checks.tasks.refresh_propagated_checks.delay"
                    ) as delay,
                    transaction.atomic(),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    Unit.objects.get(pk=unit.pk).translate(
                        self.user, "Translated", STATE_TRANSLATED, propagate=False
                    )
                delay.assert_called_once()
                groups = delay.call_args.args[1]
                self.assertEqual(
                    [group["target"] for group in groups if group["scope"] == "target"],
                    [Unit.objects.get(pk=unit.pk).target],
                )
                self.assertTrue(any(group["scope"] == "source" for group in groups))

    def test_schedule_skips_empty_targets_but_keeps_unit_refresh(self) -> None:
        for target in ("", join_plural(["", ""]), join_plural(["", "Translated"])):
            with self.subTest(target=target):
                unit = self.add_unit(self.translation_1, "empty", "Empty", target)
                with (
                    patch(
                        "weblate.checks.tasks.refresh_propagated_checks.delay"
                    ) as delay,
                    transaction.atomic(),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    schedule_propagated_checks(unit, {"reused"})
                if target == join_plural(["", "Translated"]):
                    delay.assert_called_once()
                    self.assertEqual(delay.call_args.args[1][0]["target"], target)
                else:
                    delay.assert_not_called()
                with (
                    patch(
                        "weblate.checks.tasks.refresh_propagated_checks.delay"
                    ) as delay,
                    transaction.atomic(),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    schedule_propagated_checks(unit, {"reused"}, refresh_unit=True)
                delay.assert_called_once()
                self.assertEqual(delay.call_args.args[2], [unit.pk])

    def test_worker_skips_empty_target_groups(self) -> None:
        unit = self.add_unit(self.translation_1, "empty", "Empty", "")
        with (
            patch("weblate.checks.tasks.refresh_propagated_checks.delay") as delay,
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            unit.target = "Translated"
            schedule_propagated_checks(unit, {"reused"})
        project_id, groups, unit_ids = delay.call_args.args
        for target in ("", join_plural(["", ""])):
            with self.subTest(target=target):
                groups[0]["target"] = target
                with (
                    patch.object(CHECKS["reused"], "evaluate_propagated") as evaluate,
                    patch.object(Unit, "run_checks") as run_checks,
                    patch.object(Translation, "require_full_stats_rebuild") as rebuild,
                ):
                    refresh_propagated_checks(project_id, groups, unit_ids)
                evaluate.assert_not_called()
                run_checks.assert_not_called()
                rebuild.assert_not_called()

    def test_reuse_clears_old_group_after_commit(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        edited = self.add_unit(self.translation_1, "two", "Two", "Shared")
        Check.objects.filter(unit__in=[first, edited], name="reused").delete()
        Check.objects.bulk_create(
            [Check(unit=first, name="reused"), Check(unit=edited, name="reused")]
        )
        edited = Unit.objects.get(pk=edited.pk)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            edited.translate(self.user, "Unique", STATE_TRANSLATED)
            self.assertTrue(Check.objects.filter(unit=first, name="reused").exists())
        self.assertFalse(
            Check.objects.filter(unit__in=[first, edited], name="reused").exists()
        )

    def test_consistency_updates_related_checks_after_commit(self) -> None:
        first = self.add_unit(self.translation_1, "same", "Same", "Shared")
        edited = self.add_unit(
            self.translation_2, "same", "Same", "Shared", increment=False
        )
        Check.objects.filter(unit__in=[first, edited], name="inconsistent").delete()
        edited = Unit.objects.get(pk=edited.pk)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            edited.translate(self.user, "Different", STATE_TRANSLATED, propagate=False)
            self.assertTrue(
                Check.objects.filter(unit=edited, name="inconsistent").exists()
            )
            self.assertFalse(
                Check.objects.filter(unit=first, name="inconsistent").exists()
            )
        self.assertTrue(Check.objects.filter(unit=first, name="inconsistent").exists())
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            Unit.objects.get(pk=edited.pk).translate(
                self.user, "Shared", STATE_TRANSLATED, propagate=False
            )
        self.assertFalse(
            Check.objects.filter(unit__in=[first, edited], name="inconsistent").exists()
        )

    def test_propagated_checks_deduplicate_and_preserve_dismissal(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        edited = self.add_unit(self.translation_1, "two", "Two", "Shared")
        Check.objects.filter(unit__in=[first, edited], name="reused").delete()
        dismissed = Check.objects.create(unit=first, name="reused", dismissed=True)
        unrelated = Check.objects.create(unit=edited, name="same")
        with (
            patch("weblate.checks.tasks.refresh_propagated_checks.delay") as delay,
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            schedule_propagated_checks(edited, {"reused"})
            schedule_propagated_checks(first, {"reused"})
        delay.assert_called_once()
        project_id, groups, unit_ids = delay.call_args.args
        self.assertEqual(len(groups), 1)
        refresh_propagated_checks(project_id, groups, unit_ids)
        refresh_propagated_checks(project_id, groups, unit_ids)
        dismissed.refresh_from_db()
        self.assertTrue(dismissed.dismissed)
        self.assertTrue(Check.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(
            Check.objects.filter(unit__in=[first, edited], name="reused").count(), 2
        )

    def test_repeated_refresh_repairs_source_checks(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        second = self.add_unit(self.translation_1, "two", "Two", "Shared")
        Check.objects.bulk_create(
            [Check(unit=first, name="reused"), Check(unit=second, name="reused")],
            ignore_conflicts=True,
        )
        # Model a worker that committed target warnings but failed before
        # refreshing the source warnings. Retrying must repair both.
        stale = Check.objects.create(unit=first.source_unit, name="multiple_failures")
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"reused"})
        self.assertFalse(Check.objects.filter(pk=stale.pk).exists())

    def test_propagated_checks_discard_rolled_back_savepoint(self) -> None:
        unit = self.add_unit(self.translation_1, "one", "One", "Shared")
        with (
            patch("weblate.checks.tasks.refresh_propagated_checks.delay") as delay,
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            schedule_propagated_checks(unit, {"reused"})
            with transaction.atomic():
                unit.target = "Rolled back"
                schedule_propagated_checks(unit, {"reused"})
                transaction.set_rollback(True)
        delay.assert_called_once()
        self.assertEqual(
            [group["target"] for group in delay.call_args.args[1]], ["Shared"]
        )

    def test_propagated_checks_use_latest_state(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        edited = self.add_unit(self.translation_1, "two", "Two", "")
        Check.objects.filter(unit__in=[first, edited], name="reused").delete()
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            Unit.objects.get(pk=edited.pk).translate(
                self.user, "Shared", STATE_TRANSLATED
            )
            Unit.objects.get(pk=edited.pk).translate(
                self.user, "Unique", STATE_TRANSLATED
            )
        self.assertFalse(
            Check.objects.filter(unit__in=[first, edited], name="reused").exists()
        )

    def test_propagated_checks_ignore_flags_and_case(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        second = self.add_unit(self.translation_1, "two", "Two", "Shared")
        Check.objects.filter(unit__in=[first, second], name="reused").delete()
        Unit.objects.filter(pk=first.pk).update(extra_flags="ignore-reused")
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(second, {"reused"})
        self.assertFalse(Check.objects.filter(unit=first, name="reused").exists())
        self.assertTrue(Check.objects.filter(unit=second, name="reused").exists())

        self.translation_1.language = Language.objects.get(code="he")
        self.translation_1.save()
        Unit.objects.filter(pk=first.pk).update(source="TWO")
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(Unit.objects.get(pk=second.pk), {"reused"})
        self.assertFalse(
            Check.objects.filter(unit__in=[first, second], name="reused").exists()
        )

    def test_propagated_checks_keep_enforced_check_immediate(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        edited = self.add_unit(self.translation_1, "two", "Two", "")
        self.component.enforced_checks = ["reused"]
        self.component.save()
        edited = Unit.objects.get(pk=edited.pk)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            edited.translate(self.user, "Shared", STATE_TRANSLATED)
            self.assertEqual(edited.state, STATE_NEEDS_REWRITING)
            self.assertTrue(Check.objects.filter(unit=edited, name="reused").exists())
        self.assertFalse(Check.objects.filter(unit=first, name="reused").exists())

    def test_propagated_checks_respect_group_boundaries(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        excluded = self.add_unit(self.translation_2, "two", "Two", "Shared")
        self.other.allow_translation_propagation = False
        self.other.save()
        Check.objects.filter(unit__in=[first, excluded], name="reused").delete()
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"reused"})
        self.assertFalse(
            Check.objects.filter(unit__in=[first, excluded], name="reused").exists()
        )
        self.other.allow_translation_propagation = True
        self.other.save()
        self.translation_2.plural = self.component.source_translation.plural
        self.translation_2.save()
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"reused"})
        self.assertFalse(
            Check.objects.filter(unit__in=[first, excluded], name="reused").exists()
        )

    def test_forced_source_check_refresh(self) -> None:
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        Check.objects.filter(unit__in=[first, second], name="inconsistent").delete()
        first = Unit.objects.get(pk=first.pk)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            # Simulate content propagation that must refresh the source group
            # even though the edited unit already has this warning.
            first.run_checks(skip_propagate=True)
            first.run_checks(force_propagate=True)
            self.assertFalse(
                Check.objects.filter(unit=second, name="inconsistent").exists()
            )
        self.assertTrue(Check.objects.filter(unit=second, name="inconsistent").exists())

    def test_propagated_checks_preserve_other_groups(self) -> None:
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        second = self.add_unit(self.translation_1, "two", "Two", "Shared")
        unrelated = [
            self.add_unit(
                self.translation_1,
                f"other-{index}",
                f"Other {index}",
                f"Translation {index}",
            )
            for index in range(21)
        ]
        Check.objects.bulk_create(
            [Check(unit=unit, name="reused", dismissed=True) for unit in unrelated],
            ignore_conflicts=True,
        )
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"reused"})
        self.assertTrue(Check.objects.filter(unit=second, name="reused").exists())
        self.assertEqual(
            Check.objects.filter(
                unit__in=unrelated, name="reused", dismissed=True
            ).count(),
            21,
        )

    def test_custom_propagated_check_fallback(self) -> None:
        class CustomCheck(TargetCheck):
            check_id = "custom_propagated"
            propagates = "target"

            def check_target_unit(
                self, sources: list[str], targets: list[str], unit: Unit
            ) -> bool:
                return unit.source == "Two"

        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        second = self.add_unit(self.translation_1, "two", "Two", "Shared")
        custom = CustomCheck()
        with (
            patch.dict(CHECKS.data, {custom.check_id: custom}),
            patch.dict(CHECKS.target, {custom.check_id: custom}),
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            schedule_propagated_checks(second, {custom.check_id})
        self.assertFalse(
            Check.objects.filter(unit=first, name=custom.check_id).exists()
        )
        self.assertTrue(
            Check.objects.filter(unit=second, name=custom.check_id).exists()
        )

    def test_propagated_text_updates_ordinary_checks(self) -> None:
        first = self.add_unit(self.translation_1, "same", "Same", "Original")
        edited = self.add_unit(
            self.translation_2, "same", "Same", "Original", increment=False
        )
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            Unit.objects.get(pk=edited.pk).translate(
                self.user, "Same", STATE_TRANSLATED
            )
            first.refresh_from_db()
            self.assertEqual(first.target, "Same")
            self.assertFalse(Check.objects.filter(unit=first, name="same").exists())
        self.assertTrue(Check.objects.filter(unit=first, name="same").exists())

    def test_propagated_checks_handle_deleted_units_and_removed_checks(self) -> None:
        unit = self.add_unit(self.translation_1, "one", "One", "Shared")
        with (
            patch("weblate.checks.tasks.refresh_propagated_checks.delay") as delay,
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            schedule_propagated_checks(unit, {"reused"}, refresh_unit=True)
        project_id, groups, unit_ids = delay.call_args.args
        Unit.objects.filter(pk=unit.pk).delete()
        with patch.dict(CHECKS.data):
            del CHECKS.data["reused"]
            refresh_propagated_checks(project_id, groups, unit_ids)

    def test_reuse_large_group_uses_bulk_evaluation(self) -> None:
        source_translation = self.component.source_translation
        sources = Unit.objects.bulk_create(
            [
                Unit(
                    translation=source_translation,
                    id_hash=2000 + index,
                    position=2000 + index,
                    source=f"Source {index}",
                    target=f"Source {index}",
                    state=STATE_TRANSLATED,
                )
                for index in range(520)
            ]
        )
        matching = Unit.objects.bulk_create(
            [
                Unit(
                    translation=self.translation_1,
                    source_unit=source,
                    id_hash=source.id_hash,
                    position=source.position,
                    source=source.source,
                    target="Strewberrie",
                    state=STATE_TRANSLATED,
                )
                for source in sources
            ]
        )
        edited = self.add_unit(self.translation_1, "edited", "Edited", "")
        with (
            patch.object(
                CHECKS["reused"],
                "check_target_unit",
                wraps=CHECKS["reused"].check_target_unit,
            ) as check_target,
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            # Only the edited unit is checked synchronously. The worker uses
            # the bulk evaluator, rather than one existence query per match.
            edited.translate(self.user, "Strewberrie", STATE_TRANSLATED)
            self.assertFalse(
                Check.objects.filter(unit__in=matching, name="reused").exists()
            )
        self.assertEqual(check_target.call_count, 1)
        self.assertEqual(
            Check.objects.filter(unit__in=[*matching, edited], name="reused").count(),
            521,
        )

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

    def test_consistency_empty_target(self) -> None:
        check = ConsistencyCheck()

        self.add_unit(self.translation_1, "one", "One", "Jeden")
        self.add_unit(self.translation_2, "one", "One", "", increment=False)

        self.assertNotEqual(check.check_component(self.component), [])

    def test_consistency_empty_target_run_checks(self) -> None:
        self.add_unit(self.translation_1, "one", "One", "Jeden")
        unit = self.add_unit(self.translation_2, "one", "One", "", increment=False)

        unit.run_checks()

        self.assertEqual(unit.all_checks_names, {"inconsistent"})

    def test_consistency_separates_plural_groups(self) -> None:
        self.translation_2.plural = self.other.source_translation.plural
        self.translation_2.save(update_fields=["plural"])
        unit = self.add_unit(self.translation_1, "one", "One", "Jeden")
        self.add_unit(self.translation_2, "one", "One", "One", increment=False)

        self.assertNotIn(
            unit.id_hash,
            {
                match.id_hash
                for match in ConsistencyCheck().check_component(self.component)
            },
        )

    def test_consistency_global_limit(self) -> None:
        expected = {}
        for index in range(101):
            unit = self.add_unit(self.translation_1, str(index), "Source", "First")
            other = self.add_unit(
                self.translation_2, str(index), "Source", "Second", increment=False
            )
            # Make the source translations inconsistent as well, so the same
            # hashes match in two plural groups and exercise the ordering tie.
            Unit.objects.filter(pk=other.source_unit_id).update(target="Different")
            expected[unit.id_hash, self.translation_1.plural_id] = {
                unit.pk,
                other.pk,
            }
            expected[unit.id_hash, self.component.source_translation.plural_id] = {
                unit.source_unit_id,
                other.source_unit_id,
            }

        expected_ids = set().union(*(expected[key] for key in sorted(expected)[:100]))
        self.assertSetEqual(
            {unit.pk for unit in ConsistencyCheck().check_component(self.component)},
            expected_ids,
        )

    def test_consistency_query_uses_min_max_targets(self) -> None:
        check = ConsistencyCheck()

        self.add_unit(self.translation_1, "one", "One", "Jeden")
        self.add_unit(self.translation_2, "one", "One", "Jedna", increment=False)

        with CaptureQueriesContext(connection) as queries:
            list(check.check_component(self.component))

        sql = "\n".join(query["sql"].upper() for query in queries)
        self.assertNotIn("COUNT(DISTINCT", sql)
        self.assertIn("MIN(", sql)
        self.assertIn("MAX(", sql)

        aggregate_sql = next(
            query["sql"].upper() for query in queries if "MIN(" in query["sql"].upper()
        )
        self.assertNotIn('"TRANS_COMPONENT"', aggregate_sql)
        self.assertNotIn('"TRANS_TRANSLATION"', aggregate_sql)
        self.assertNotIn("COALESCE(", aggregate_sql)
        self.assertNotIn("'BLOCKED'", aggregate_sql)
        self.assertIn('"TRANS_UNIT"."TRANSLATION_ID" IN', aggregate_sql)

        unit_sql = next(
            query["sql"].upper()
            for query in queries
            if '"TRANS_UNIT"."TRANSLATION_ID" IN' in query["sql"].upper()
            and '"TRANS_UNIT"."ID_HASH" IN' in query["sql"].upper()
            and "MIN(" not in query["sql"].upper()
        )
        self.assertNotIn('"TRANS_COMPONENT"', unit_sql)
        self.assertNotIn('"TRANS_TRANSLATION"', unit_sql)

    def test_consistency_skips_singleton_plurals(self) -> None:
        check = ConsistencyCheck()
        self.other.allow_translation_propagation = False
        self.other.save(update_fields=["allow_translation_propagation"])

        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(check.check_component(self.component), [])

        sql = "\n".join(query["sql"].upper() for query in queries)
        self.assertNotIn("MIN(", sql)
