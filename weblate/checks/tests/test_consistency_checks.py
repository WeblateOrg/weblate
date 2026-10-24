# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for consistency checks."""

from __future__ import annotations

from hashlib import md5
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

from django.db import connection, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Role
from weblate.auth.results import Denied
from weblate.checks.base import TargetCheck
from weblate.checks.consistency import (
    ConsistencyCheck,
    PluralsCheck,
    ReusedCheck,
    SamePluralsCheck,
    TranslatedCheck,
)
from weblate.checks.models import CHECKS, Check
from weblate.checks.tasks import (
    _get_propagated_check_units,
    refresh_propagated_checks,
    schedule_propagated_checks,
)
from weblate.lang.models import Language, Plural
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Project, Translation, Unit, WorkflowSetting
from weblate.trans.models.pending import PendingUnitChange
from weblate.trans.models.project import CommitPolicyChoices
from weblate.trans.tests.factories import make_unit
from weblate.trans.tests.test_views import (
    FixtureTestCase,
    ReusableComponentTestCase,
)
from weblate.trans.tests.utils import create_another_user, get_test_actor
from weblate.trans.util import join_plural
from weblate.utils.change_origin import acting_user_context
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.trans.tests.test_views import ComponentTestCase


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
        unit.change_set.create(
            user=get_test_actor(self), action=ActionEvents.SOURCE_CHANGE
        )
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


class ConsistencyUnitsMixin:
    _id_hash: int

    def add_unit(
        self,
        translation: Translation,
        context: str,
        source: str,
        target: str,
        increment: bool = True,
    ) -> Unit:
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


class ConsistencyCheckTest(ConsistencyUnitsMixin, ReusableComponentTestCase):
    _fixture_other_pk: int

    @classmethod
    def build_fixture(cls, builder: ComponentTestCase) -> None:
        super().build_fixture(builder)
        cls._fixture_other_pk = builder.create_link_existing().pk

    def setUp(self) -> None:
        super().setUp()
        self.other = Component.objects.get(pk=self._fixture_other_pk)
        self.translation_1 = self.component.translation_set.get(language__code="cs")
        self.translation_2 = self.other.translation_set.get(language__code="cs")
        self._id_hash = 1000

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

    def test_batch_checks_exclude_ineligible_translations(self) -> None:
        self.add_unit(self.translation_1, "same", "Same", "First")
        self.add_unit(self.translation_2, "same", "Same", "Second", increment=False)
        self.add_unit(self.translation_1, "one", "One", "Shared")
        self.add_unit(self.translation_2, "two", "Two", "Shared")

        for check in (ConsistencyCheck(), ReusedCheck()):
            self.assertNotEqual(list(check.check_component(self.component)), [])

        Component.objects.filter(pk=self.other.pk).update(
            allow_translation_propagation=False
        )
        for check in (ConsistencyCheck(), ReusedCheck()):
            with self.subTest(check=check.check_id, boundary="disabled"):
                self.assertEqual(list(check.check_component(self.component)), [])

        other_project = self.create_project(name="Other", slug="other")
        Component.objects.filter(pk=self.other.pk).update(
            project=other_project, allow_translation_propagation=True
        )
        for check in (ConsistencyCheck(), ReusedCheck()):
            with self.subTest(check=check.check_id, boundary="project"):
                self.assertEqual(list(check.check_component(self.component)), [])

    def test_reuse_batch_compares_languages_with_shared_plural_rules(self) -> None:
        hebrew = Language.objects.get(code="he")
        Translation.objects.filter(pk=self.translation_2.pk).update(language=hebrew)
        self.translation_2.language = hebrew
        first = self.add_unit(self.translation_1, "one", "One", "Shared")
        second = self.add_unit(self.translation_2, "two", "one", "Shared")

        # The Czech unit sees distinct sources; Hebrew ignores source casing.
        check = ReusedCheck()
        self.assertTrue(check.check_target_unit([], [], first))
        self.assertFalse(check.check_target_unit([], [], second))
        self.assertEqual(list(check.check_component(self.component)), [first])

    def test_consistency_batch_separates_target_languages(self) -> None:
        hebrew = Language.objects.get(code="he")
        Translation.objects.filter(pk=self.translation_2.pk).update(language=hebrew)
        self.translation_2.language = hebrew
        self.add_unit(self.translation_1, "same", "Same", "First")
        self.add_unit(self.translation_2, "same", "Same", "Second", increment=False)

        self.assertEqual(list(ConsistencyCheck().check_component(self.component)), [])

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

    def test_reuse_respects_restricted_component_boundary(self) -> None:
        check = ReusedCheck()
        visible = self.add_unit(
            self.translation_1, "visible", "Visible source", "Shared"
        )
        hidden = self.add_unit(self.translation_2, "hidden", "Hidden source", "Shared")
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        self.other.restricted = True
        hidden.translation.component.restricted = True

        self.assertFalse(check.check_target_unit([], [], visible))
        self.assertTrue(check.check_target_unit([], [], hidden))
        self.assertEqual(list(check.check_component(self.component)), [hidden])
        self.assertNotIn(
            "Hidden source", str(check.get_description(Check(unit=visible)))
        )
        self.assertIn("Visible source", str(check.get_description(Check(unit=hidden))))

        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(visible, {"reused"})
        self.assertFalse(Check.objects.filter(unit=visible, name="reused").exists())
        self.assertTrue(Check.objects.filter(unit=hidden, name="reused").exists())

        visible.run_checks()
        self.client.logout()
        response = self.client.get(
            f"{visible.translation.get_translate_url()}?checksum={visible.checksum}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden source")
        self.assertNotContains(response, "Reused translation")

    def test_reuse_within_restricted_component(self) -> None:
        check = ReusedCheck()
        first = self.add_unit(self.translation_2, "one", "One", "Shared")
        second = self.add_unit(self.translation_2, "two", "Two", "Shared")
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        self.other.restricted = True
        first.translation.component.restricted = True
        second.translation.component.restricted = True

        self.assertTrue(check.check_target_unit([], [], first))
        self.assertCountEqual(check.check_component(self.component), [first, second])

    def test_reuse_does_not_compare_different_restricted_components(self) -> None:
        check = ReusedCheck()
        third = self.create_link_existing(name="Third", slug="third")
        third_translation = third.translation_set.get(language__code="cs")
        first = self.add_unit(self.translation_2, "one", "First secret", "Shared")
        second = self.add_unit(third_translation, "two", "Second secret", "Shared")
        Component.objects.filter(pk__in=[self.other.pk, third.pk]).update(
            restricted=True
        )
        first.translation.component.restricted = True
        second.translation.component.restricted = True

        self.assertFalse(check.check_target_unit([], [], first))
        self.assertFalse(check.check_target_unit([], [], second))
        self.assertEqual(list(check.check_component(self.component)), [])
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"reused"})
        self.assertFalse(
            Check.objects.filter(unit__in=[first, second], name="reused").exists()
        )

    def test_restricting_component_removes_stale_visible_checks(self) -> None:
        visible = self.add_unit(self.translation_1, "visible", "Visible", "Shared")
        self.add_unit(self.translation_2, "hidden", "Hidden", "Shared")
        stale = Check.objects.bulk_create(
            [
                Check(unit=visible, name="reused"),
                Check(unit=visible, name="inconsistent"),
            ]
        )

        self.other.restricted = True
        self.enterContext(acting_user_context(self.user))
        with patch(
            "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
        ) as schedule:
            self.other.save(update_fields=["restricted"])

        self.assertFalse(
            Check.objects.filter(pk__in=[check.pk for check in stale]).exists()
        )
        schedule.assert_called_once_with(
            self.component.pk, [], ["inconsistent", "reused"], batch_mode=True
        )

    def test_restricting_component_removes_stale_restricted_checks(self) -> None:
        visible = self.add_unit(self.translation_1, "visible", "Visible", "Shared")
        hidden = self.add_unit(self.translation_2, "hidden", "Hidden", "Shared")
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        self.other.restricted = True
        stale, _ = Check.objects.get_or_create(unit=hidden, name="reused")

        self.component.restricted = True
        self.enterContext(acting_user_context(self.user))
        with patch("weblate.checks.tasks.finalize_component_checks.delay_on_commit"):
            self.component.save(update_fields=["restricted"])

        self.assertFalse(Check.objects.filter(pk=stale.pk).exists())
        self.assertFalse(ReusedCheck().check_target_unit([], [], visible))

    def test_restricting_component_preserves_unrelated_dismissal(self) -> None:
        third = self.create_link_existing(name="Third", slug="third")
        third_translation = third.translation_set.get(language__code="cs")
        first = self.add_unit(self.translation_1, "first", "First", "Shared")
        self.add_unit(third_translation, "second", "Second", "Shared")
        dismissed, _ = Check.objects.update_or_create(
            unit=first, name="reused", defaults={"dismissed": True}
        )

        self.other.restricted = True
        self.enterContext(acting_user_context(self.user))
        with patch("weblate.checks.tasks.finalize_component_checks.delay_on_commit"):
            self.other.save(update_fields=["restricted"])

        dismissed.refresh_from_db()
        self.assertTrue(dismissed.dismissed)

    def test_restricting_component_queues_only_enabled_checks(self) -> None:
        self.other.restricted = True
        self.enterContext(acting_user_context(self.user))
        with (
            patch.dict(CHECKS.data, {"reused": CHECKS["reused"]}, clear=True),
            patch(
                "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
            ) as schedule,
        ):
            self.other.save(update_fields=["restricted"])
        schedule.assert_called_once_with(
            self.component.pk, [], ["reused"], batch_mode=True
        )

    def test_restricting_component_with_checks_disabled(self) -> None:
        visible = self.add_unit(self.translation_1, "visible", "Visible", "Shared")
        self.add_unit(self.translation_2, "hidden", "Hidden", "Shared")
        Check.objects.update_or_create(unit=visible, name="reused")
        self.other.restricted = True
        self.enterContext(acting_user_context(self.user))
        with (
            patch.dict(CHECKS.data, {}, clear=True),
            patch(
                "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
            ) as schedule,
        ):
            self.other.save(update_fields=["restricted"])
        schedule.assert_not_called()
        self.assertFalse(Check.objects.filter(unit=visible, name="reused").exists())

    def test_project_move_cleans_both_projects(self) -> None:
        target_project = self.create_project(name="Other", slug="other")
        visible = self.add_unit(self.translation_1, "visible", "Visible", "Shared")
        hidden = self.add_unit(self.translation_2, "hidden", "Hidden", "Shared")
        old_check, _ = Check.objects.get_or_create(unit=visible, name="reused")
        moved_check, _ = Check.objects.get_or_create(unit=hidden, name="reused")

        self.other.project = target_project
        self.other.restricted = True
        self.enterContext(acting_user_context(self.user))
        with patch(
            "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
        ) as schedule:
            self.other.save(update_fields=["project", "restricted"])

        self.assertFalse(Check.objects.filter(pk=old_check.pk).exists())
        self.assertFalse(Check.objects.filter(pk=moved_check.pk).exists())
        self.assertCountEqual(
            [call.args[0] for call in schedule.call_args_list],
            [self.component.pk, self.other.pk],
        )

    def test_project_move_alone_cleans_old_project(self) -> None:
        target_project = self.create_project(name="Other", slug="other")
        visible = self.add_unit(self.translation_1, "visible", "Visible", "Shared")
        self.add_unit(self.translation_2, "hidden", "Hidden", "Shared")
        stale, _ = Check.objects.get_or_create(unit=visible, name="reused")

        self.other.project = target_project
        self.enterContext(acting_user_context(self.user))
        with patch("weblate.checks.tasks.finalize_component_checks.delay_on_commit"):
            self.other.save(update_fields=["project"])

        self.assertFalse(Check.objects.filter(pk=stale.pk).exists())

    def test_restriction_cleanup_does_not_evaluate_checks_one_by_one(self) -> None:
        for index in range(30):
            visible = self.add_unit(
                self.translation_1, f"visible-{index}", f"Visible {index}", "Shared"
            )
            self.add_unit(
                self.translation_2, f"hidden-{index}", f"Hidden {index}", "Shared"
            )
            Check.objects.update_or_create(unit=visible, name="reused")
        self.other.restricted = True
        self.enterContext(acting_user_context(self.user))
        with (
            patch.object(ReusedCheck, "check_target_unit") as reused,
            patch.object(ConsistencyCheck, "check_target_unit") as inconsistent,
            patch("weblate.checks.tasks.finalize_component_checks.delay_on_commit"),
        ):
            self.other.save(update_fields=["restricted"])
        reused.assert_not_called()
        inconsistent.assert_not_called()

    def test_dismissal_does_not_propagate_to_restricted_peer(self) -> None:
        visible = self.add_unit(self.translation_1, "same", "Same", "First")
        hidden = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        self.other.restricted = True
        visible_check, _ = Check.objects.get_or_create(
            unit=visible, name="inconsistent"
        )
        hidden_check, _ = Check.objects.get_or_create(unit=hidden, name="inconsistent")
        Check.objects.filter(pk__in=[visible_check.pk, hidden_check.pk]).update(
            dismissed=False
        )

        visible_check.set_dismiss()

        hidden_check.refresh_from_db()
        self.assertFalse(hidden_check.dismissed)

    def test_reuse_limit_counts_visible_matches(self) -> None:
        third = self.create_link_existing(name="Third", slug="third")
        third_translation = third.translation_set.get(language__code="cs")
        Component.objects.filter(pk__in=[self.other.pk, third.pk]).update(
            restricted=True
        )
        self.other.restricted = True
        third.restricted = True
        targets = [f"Target {index}" for index in range(61)]
        visible_target = max(
            targets,
            key=lambda value: md5(
                value.lower().encode(), usedforsecurity=False
            ).hexdigest(),
        )
        for target in targets:
            self.add_unit(self.translation_2, f"one-{target}", f"One {target}", target)
            self.add_unit(third_translation, f"two-{target}", f"Two {target}", target)
        first = self.add_unit(
            self.translation_1, "visible-one", "Visible one", visible_target
        )
        second = self.add_unit(
            self.translation_1, "visible-two", "Visible two", visible_target
        )

        with CaptureQueriesContext(connection) as queries:
            result = {unit.pk for unit in ReusedCheck().check_component(self.component)}
        self.assertTrue({first.pk, second.pk} <= result)
        self.assertEqual(
            sum(
                "LIMIT 20" in query["sql"] and "EXISTS(" in query["sql"]
                for query in queries
            ),
            1,
        )

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
        self.enterContext(acting_user_context(self.user))
        self.other.save()
        Check.objects.filter(unit__in=[first, excluded], name="reused").delete()
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"reused"})
        self.assertFalse(
            Check.objects.filter(unit__in=[first, excluded], name="reused").exists()
        )
        self.other.allow_translation_propagation = True
        self.enterContext(acting_user_context(self.user))
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

    def test_consistency_respects_restricted_component_boundary(self) -> None:
        check = ConsistencyCheck()
        visible = self.add_unit(self.translation_1, "same", "Same", "Visible")
        hidden = self.add_unit(
            self.translation_2, "same", "Same", "Secret", increment=False
        )
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        self.other.restricted = True
        hidden.translation.component.restricted = True

        self.assertFalse(check.check_target_unit([], [], visible))
        self.assertTrue(check.check_target_unit([], [], hidden))
        self.assertEqual(list(check.check_component(self.component)), [hidden])

        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(visible, {"inconsistent"})
        self.assertFalse(
            Check.objects.filter(unit=visible, name="inconsistent").exists()
        )
        self.assertTrue(Check.objects.filter(unit=hidden, name="inconsistent").exists())

        visible.run_checks()
        self.client.logout()
        response = self.client.get(
            f"{visible.translation.get_translate_url()}?checksum={visible.checksum}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Inconsistent")

    def test_consistency_separates_restricted_components(self) -> None:
        check = ConsistencyCheck()
        third = self.create_link_existing(name="Third", slug="third")
        third_translation = third.translation_set.get(language__code="cs")
        first = self.add_unit(self.translation_2, "same", "Same", "First")
        second = self.add_unit(
            third_translation, "same", "Same", "Second", increment=False
        )
        Component.objects.filter(pk__in=[self.other.pk, third.pk]).update(
            restricted=True
        )
        first.translation.component.restricted = True
        second.translation.component.restricted = True

        self.assertFalse(check.check_target_unit([], [], first))
        self.assertFalse(check.check_target_unit([], [], second))
        self.assertEqual(list(check.check_component(self.component)), [])
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {"inconsistent"})
        self.assertFalse(
            Check.objects.filter(unit__in=[first, second], name="inconsistent").exists()
        )

    def test_consistency_untranslated_unit_respects_restriction(self) -> None:
        check = ConsistencyCheck()
        visible = self.add_unit(self.translation_1, "same", "Same", "")
        hidden = self.add_unit(
            self.translation_2, "same", "Same", "Secret", increment=False
        )
        Unit.objects.filter(pk=visible.pk).update(state=STATE_EMPTY)
        visible.state = STATE_EMPTY
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        hidden.translation.component.restricted = True

        self.assertFalse(check.check_target_unit([], [], visible))
        self.assertTrue(check.check_target_unit([], [], hidden))
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(visible, {"inconsistent"})
        self.assertFalse(
            Check.objects.filter(unit=visible, name="inconsistent").exists()
        )
        self.assertTrue(Check.objects.filter(unit=hidden, name="inconsistent").exists())

    def test_consistency_keeps_visible_component_comparisons(self) -> None:
        check = ConsistencyCheck()
        third = self.create_link_existing(name="Third", slug="third")
        third_translation = third.translation_set.get(language__code="cs")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            third_translation, "same", "Same", "Second", increment=False
        )
        self.assertTrue(check.check_target_unit([], [], first))
        self.assertCountEqual(check.check_component(self.component), [first, second])

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
            source = unit.source_unit
            other_source = other.source_unit
            assert source is not None
            assert other_source is not None
            Unit.objects.filter(pk=other_source.pk).update(target="Different")
            expected[unit.id_hash, self.translation_1.plural_id] = {
                unit.pk,
                other.pk,
            }
            expected[unit.id_hash, self.component.source_translation.plural_id] = {
                source.pk,
                other_source.pk,
            }

        expected_ids = set().union(*(expected[key] for key in sorted(expected)[:100]))
        self.assertSetEqual(
            {unit.pk for unit in ConsistencyCheck().check_component(self.component)},
            expected_ids,
        )

    def test_consistency_limit_counts_visible_matches(self) -> None:
        third = self.create_link_existing(name="Third", slug="third")
        third_translation = third.translation_set.get(language__code="cs")
        Component.objects.filter(pk__in=[self.other.pk, third.pk]).update(
            restricted=True
        )
        self.other.restricted = True
        third.restricted = True
        for index in range(101):
            self.add_unit(self.translation_2, str(index), "Source", "First")
            hidden = self.add_unit(
                third_translation, str(index), "Source", "Second", increment=False
            )
        self.add_unit(self.translation_1, "100", "Source", "First", increment=False)

        with CaptureQueriesContext(connection) as queries:
            result = {
                unit.pk for unit in ConsistencyCheck().check_component(self.component)
            }
        self.assertIn(hidden.pk, result)
        self.assertEqual(
            sum(
                "LIMIT 100" in query["sql"] and "EXISTS(" in query["sql"]
                for query in queries
            ),
            1,
        )

    def test_consistency_query_limits_visible_matches(self) -> None:
        check = ConsistencyCheck()

        self.add_unit(self.translation_1, "one", "One", "Jeden")
        self.add_unit(self.translation_2, "one", "One", "Jedna", increment=False)

        with CaptureQueriesContext(connection) as queries:
            list(check.check_component(self.component))

        sql = "\n".join(query["sql"].upper() for query in queries)
        self.assertIn("EXISTS(", sql)
        self.assertIn("LIMIT 100", sql)
        self.assertIn("SELECT DISTINCT", sql)

        unit_sql = next(
            query["sql"].upper()
            for query in queries
            if '"TRANS_UNIT"."TRANSLATION_ID" IN' in query["sql"].upper()
            and '"TRANS_UNIT"."ID_HASH" IN' in query["sql"].upper()
            and "EXISTS(" not in query["sql"].upper()
        )
        self.assertNotIn('"TRANS_COMPONENT"', unit_sql)
        self.assertNotIn('"TRANS_TRANSLATION"', unit_sql)

    def test_consistency_skips_singleton_plurals(self) -> None:
        check = ConsistencyCheck()
        self.other.allow_translation_propagation = False
        self.enterContext(acting_user_context(self.user))
        self.other.save(update_fields=["allow_translation_propagation"])

        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(check.check_component(self.component), [])

        sql = "\n".join(query["sql"].upper() for query in queries)
        self.assertNotIn("MIN(", sql)


class WorkspacePropagationTest(ConsistencyUnitsMixin, ReusableComponentTestCase):
    _fixture_other_pk: int

    @classmethod
    def build_fixture(cls, builder: ComponentTestCase) -> None:
        super().build_fixture(builder)
        cls._fixture_other_pk = builder.create_link_existing().pk

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(acting_user_context(self.user))
        self.workspace = Workspace.objects.create(name="Propagation workspace")
        self.other_project = self.create_project(
            name="Other project", slug="other-project", workspace=self.workspace
        )
        Project.objects.filter(pk=self.project.pk).update(workspace=self.workspace)
        Component.objects.filter(pk=self._fixture_other_pk).update(
            project=self.other_project, name=self.component.name
        )
        self._id_hash = 1000
        self.translation_1 = self.component.translation_set.get(language__code="cs")
        self.other = Component.objects.get(pk=self._fixture_other_pk)
        self.translation_2 = self.other.translation_set.get(language__code="cs")

    def set_scope(self, scope: str) -> None:
        type(self.workspace).objects.filter(pk=self.workspace.pk).update(
            propagation_scope=scope
        )

    def test_scope_and_name_matching(self) -> None:
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        for scope, name, matches in (
            ("project", self.component.name, False),
            ("workspace", "Different", True),
            ("component_name", self.component.name, True),
            ("component_name", self.component.name.upper(), False),
            ("component_name", "Different", False),
        ):
            with self.subTest(scope=scope, name=name):
                self.set_scope(scope)
                Component.objects.filter(pk=self.other.pk).update(name=name)
                self.assertEqual(
                    Unit.objects.get(pk=first.pk)
                    .propagated_units.filter(pk=second.pk)
                    .exists(),
                    matches,
                )
        self.set_scope("workspace")
        Project.objects.filter(pk=self.other_project.pk).update(workspace=None)
        self.assertNotIn(second, Unit.objects.get(pk=first.pk).propagated_units)

    def test_project_without_workspace(self) -> None:
        self.set_scope("workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=None)
        Component.objects.filter(pk=self.other.pk).update(
            project=self.project, name="Other component"
        )
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        self.assertIn(second, Unit.objects.get(pk=first.pk).propagated_units)

    def test_edit_propagates_state_and_actor(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            Unit.objects.get(pk=first.pk).translate(
                self.user, "Changed", STATE_TRANSLATED
            )
        second.refresh_from_db()
        self.assertEqual(second.target, "Changed")
        self.assertEqual(second.state, STATE_TRANSLATED)
        self.assertEqual(
            second.change_set.get(action=ActionEvents.PROPAGATED_EDIT).user, self.user
        )

    def test_destination_exclusion(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        Component.objects.filter(pk=self.other.pk).update(
            allow_translation_propagation=False
        )
        Unit.objects.get(pk=first.pk).translate(self.user, "Changed", STATE_TRANSLATED)
        second.refresh_from_db()
        self.assertEqual(second.target, "Second")

    def test_destination_permissions(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        with patch.object(type(self.user), "has_perm", return_value=False):
            first.target = "Changed"
            self.assertFalse(first.propagate(self.user))
        second.refresh_from_db()
        self.assertEqual(second.target, "Second")

    def check_visibility(
        self, check, first, second, expected: bool, second_expected: bool | None = None
    ) -> None:
        if second_expected is None:
            second_expected = expected
        first = Unit.objects.get(pk=first.pk)
        second = Unit.objects.get(pk=second.pk)
        self.assertEqual(check.check_target_unit([], [], first), expected)
        result = {
            unit.pk for unit in check.check_component(first.translation.component)
        }
        self.assertEqual(first.pk in result, expected)
        self.assertEqual(second.pk in result, second_expected)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            schedule_propagated_checks(first, {check.check_id})
        self.assertEqual(
            Check.objects.filter(unit=first, name=check.check_id).exists(), expected
        )
        self.assertEqual(
            Check.objects.filter(unit=second, name=check.check_id).exists(),
            second_expected,
        )

    def test_consistency_visibility(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        for access in (
            Project.ACCESS_PUBLIC,
            Project.ACCESS_PROTECTED,
            Project.ACCESS_PRIVATE,
            Project.ACCESS_CUSTOM,
        ):
            with self.subTest(access=access):
                Project.objects.filter(pk=self.other_project.pk).update(
                    access_control=access
                )
                self.check_visibility(
                    ConsistencyCheck(),
                    first,
                    second,
                    access in {Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED},
                )

    def test_reused_visibility_and_description(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "first", "First source", "Shared")
        second = self.add_unit(self.translation_2, "second", "Secret source", "Shared")
        for access in (Project.ACCESS_PUBLIC, Project.ACCESS_PRIVATE):
            with self.subTest(access=access):
                Project.objects.filter(pk=self.other_project.pk).update(
                    access_control=access
                )
                self.check_visibility(
                    ReusedCheck(), first, second, access == Project.ACCESS_PUBLIC
                )
                description = ReusedCheck().get_description(
                    Check(unit=Unit.objects.get(pk=first.pk))
                )
                self.assertEqual(
                    "Secret source" in description, access == Project.ACCESS_PUBLIC
                )

    def test_restricted_component_visibility(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        Component.objects.filter(pk=self.other.pk).update(restricted=True)
        self.check_visibility(ConsistencyCheck(), first, second, False, True)

    def test_named_check_groups_do_not_mix(self) -> None:
        self.set_scope("component_name")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        self.check_visibility(ConsistencyCheck(), first, second, True)
        self.other.name = "Different"
        with patch("weblate.checks.tasks.finalize_component_checks.delay_on_commit"):
            self.other.save(update_fields=["name"])
        self.check_visibility(ConsistencyCheck(), first, second, False)

    def test_scope_change_removes_warnings_without_changing_translations(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        Check.objects.get_or_create(unit=first, name="inconsistent")
        Check.objects.get_or_create(unit=second, name="inconsistent")
        self.workspace.propagation_scope = "project"
        with patch(
            "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
        ) as schedule:
            self.workspace.save(update_fields=["propagation_scope"])
        self.assertTrue(schedule.called)
        self.assertFalse(
            Check.objects.filter(unit__in=[first, second], name="inconsistent").exists()
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.target, second.target), ("First", "Second"))

    def test_boundary_change_removes_warnings(self) -> None:
        self.set_scope("component_name")
        first = self.add_unit(self.translation_1, "first", "First source", "Shared")
        second = self.add_unit(self.translation_2, "second", "Second source", "Shared")
        for boundary in (
            "name",
            "allow_translation_propagation",
            "restricted",
            "access_control",
            "workspace",
        ):
            with self.subTest(boundary=boundary):
                Component.objects.filter(pk=self.other.pk).update(
                    name=self.component.name,
                    allow_translation_propagation=True,
                    restricted=False,
                )
                Project.objects.filter(pk=self.other_project.pk).update(
                    workspace=self.workspace, access_control=Project.ACCESS_PUBLIC
                )
                Check.objects.get_or_create(unit=first, name="reused")
                Check.objects.get_or_create(unit=second, name="reused")
                obj: Project | Component
                if boundary in {"access_control", "workspace"}:
                    obj = Project.objects.get(pk=self.other_project.pk)
                    setattr(
                        obj,
                        boundary,
                        Project.ACCESS_PRIVATE
                        if boundary == "access_control"
                        else None,
                    )
                else:
                    obj = Component.objects.get(pk=self.other.pk)
                    setattr(
                        obj,
                        boundary,
                        {
                            "name": "Renamed",
                            "allow_translation_propagation": False,
                            "restricted": True,
                        }[boundary],
                    )
                with patch(
                    "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
                ):
                    obj.save(update_fields=[boundary])
                self.assertFalse(
                    Check.objects.filter(unit=first, name="reused").exists()
                )
                self.assertEqual(
                    Check.objects.filter(unit=second, name="reused").exists(),
                    boundary == "restricted",
                )

    def test_worker_uses_current_group_membership(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        with (
            patch("weblate.checks.tasks.refresh_propagated_checks.delay") as schedule,
            transaction.atomic(),
            self.captureOnCommitCallbacks(execute=True),
        ):
            schedule_propagated_checks(first, {"inconsistent"})
        self.workspace.propagation_scope = "project"
        with patch("weblate.checks.tasks.finalize_component_checks.delay_on_commit"):
            self.workspace.save(update_fields=["propagation_scope"])
        refresh_propagated_checks(*schedule.call_args.args)
        self.assertFalse(
            Check.objects.filter(unit__in=[first, second], name="inconsistent").exists()
        )

    def test_worker_discards_groups_without_newly_required_source_rules(self) -> None:
        for check_id in ("inconsistent", "reused"):
            with self.subTest(check_id=check_id):
                self.set_scope("project")
                first = self.add_unit(
                    self.translation_1, check_id, "First source", "Shared"
                )
                second = self.add_unit(
                    self.translation_2,
                    check_id,
                    "First source" if check_id == "inconsistent" else "Second source",
                    "Different" if check_id == "inconsistent" else "Shared",
                    increment=False,
                )
                source_translation = second.source_unit.translation
                original_plural = source_translation.plural
                plural, _created = Plural.objects.get_or_create(
                    language=source_translation.language,
                    number=original_plural.number,
                    formula="n > 1",
                    type=original_plural.type,
                )
                Translation.objects.filter(pk=source_translation.pk).update(
                    plural=plural
                )
                with (
                    patch(
                        "weblate.checks.tasks.refresh_propagated_checks.delay"
                    ) as delay,
                    transaction.atomic(),
                    self.captureOnCommitCallbacks(execute=True),
                ):
                    schedule_propagated_checks(first, {check_id})
                project_id, groups, unit_ids = delay.call_args.args
                self.assertTrue(groups)
                self.assertTrue(all("source_rules" not in group for group in groups))
                self.workspace.propagation_scope = "workspace"
                with patch(
                    "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
                ):
                    self.workspace.save(update_fields=["propagation_scope"])
                check = (
                    ConsistencyCheck() if check_id == "inconsistent" else ReusedCheck()
                )
                check.perform_batch(Component.objects.get(pk=self.component.pk))
                for group in groups:
                    self.assertFalse(
                        _get_propagated_check_units(project_id, group).exists()
                    )
                refresh_propagated_checks(project_id, groups, unit_ids)
                self.assertFalse(
                    Check.objects.filter(
                        unit__in=[first, second], name=check_id
                    ).exists()
                )

    def test_upload_propagates_across_projects(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        request = cast("AuthenticatedHttpRequest", RequestFactory().post("/"))
        request.user = self.user
        uploaded = SimpleNamespace(
            source=first.source,
            context=first.context,
            target="Uploaded",
            import_id_hash=first.id_hash,
            target_plural_forms=(),
        )
        store = Mock(content_units=[uploaded])
        store.iterate_merge.return_value = [(False, uploaded)]
        self.translation_1.merge_translations(
            request, self.user, store, "replace-translated", "translate", ""
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.target, second.target), ("Uploaded", "Uploaded"))

    def test_mixed_translation_parent_configuration(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Original", "First")
        german = Language.objects.get(code="de")
        parent = self.component.translation_set.get(language=german).unit_set.create(
            id_hash=first.id_hash,
            position=first.position,
            source_unit=first.source_unit,
            source=first.source,
            context=first.context,
            target="German source",
            state=STATE_TRANSLATED,
        )
        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation_1.language,
            source_language=german,
        )
        Component.objects.filter(pk=self.other.pk).update(source_language=german)
        self.other.source_language = german
        self.translation_2.component = self.other
        second = self.add_unit(self.translation_2, "same", "German source", "Second")
        first = Unit.objects.get(pk=first.pk)
        self.assertEqual(first.translation_parent_id, parent.pk)
        self.assertIn(second, first.propagated_units)
        self.assertIn(first, Unit.objects.get(pk=second.pk).propagated_units)
        self.check_visibility(ConsistencyCheck(), first, second, True)
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            first.translate(self.user, "Changed", STATE_TRANSLATED)
        second.refresh_from_db()
        self.assertEqual(second.target, "Changed")

    def test_inaccessible_destination_is_not_named_in_warnings(self) -> None:
        self.set_scope("workspace")
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        self.add_unit(self.translation_2, "same", "Same", "Second", increment=False)
        with (
            patch.object(
                type(self.user), "has_perm", return_value=Denied("Access denied")
            ),
            patch.object(type(self.user), "can_access_component", return_value=False),
            patch("weblate.trans.models.unit.messages.warning") as warning,
        ):
            self.assertFalse(first.propagate(self.user, request=Mock()))
        warning.assert_not_called()

    def create_review_units(self) -> tuple[Unit, Unit, User, Group]:
        self.set_scope("workspace")
        Project.objects.filter(pk__in=[self.project.pk, self.other_project.pk]).update(
            translation_review=True
        )
        first = self.add_unit(self.translation_1, "same", "Same", "First")
        second = self.add_unit(
            self.translation_2, "same", "Same", "Second", increment=False
        )
        user = create_another_user()
        editors = Group.objects.create(
            name="Propagation editors", language_selection=SELECTION_ALL
        )
        editors.roles.add(Role.objects.get(name="Translate"))
        editors.projects.add(self.project, self.other_project)
        reviewers = Group.objects.create(
            name="Source reviewers", language_selection=SELECTION_ALL
        )
        reviewers.roles.add(Role.objects.get(name="Review strings"))
        reviewers.projects.add(self.project)
        user.groups.set([editors, reviewers])
        user.clear_permissions_cache()
        first = Unit.objects.get(pk=first.pk)
        second = Unit.objects.get(pk=second.pk)
        self.assertTrue(user.has_perm("unit.review", first))
        self.assertTrue(user.has_perm("unit.edit", second))
        self.assertFalse(user.has_perm("unit.review", second))
        return first, second, user, reviewers

    def test_approval_uses_each_destination_review_permission(self) -> None:
        first, second, user, reviewers = self.create_review_units()
        third_project = self.create_project(
            name="Reviewed destination",
            slug="reviewed-destination",
            workspace=self.workspace,
            translation_review=True,
        )
        third_component = self.create_link_existing(project=third_project)
        third_translation = third_component.translation_set.get(language__code="cs")
        third = self.add_unit(
            third_translation, "same", "Same", "Third", increment=False
        )
        reviewers.projects.add(third_project)
        user.clear_permissions_cache()
        self.assertTrue(user.has_perm("unit.review", third))
        with transaction.atomic(), self.captureOnCommitCallbacks(execute=True):
            first.translate(user, "Approved source", STATE_APPROVED)
        for unit, state in ((second, STATE_TRANSLATED), (third, STATE_APPROVED)):
            with self.subTest(destination=unit.pk):
                unit.refresh_from_db()
                self.assertEqual(unit.target, first.target)
                self.assertEqual(unit.state, state)
                self.assertEqual(unit.original_state, state)
                pending = PendingUnitChange.objects.get(unit=unit, target=first.target)
                self.assertEqual(pending.state, state)
                self.assertEqual(pending.metadata["actor_id"], user.pk)
                change = unit.change_set.get(action=ActionEvents.PROPAGATED_EDIT)
                self.assertEqual(change.user, user)
                self.assertEqual(change.details["state"], state)

    def test_approval_fallback_respects_destination_review_settings(self) -> None:
        first, second, user, reviewers = self.create_review_units()
        reviewers.projects.add(self.other_project)
        for workflow_override in (False, True):
            with self.subTest(workflow_override=workflow_override):
                Project.objects.filter(pk=self.other_project.pk).update(
                    translation_review=workflow_override
                )
                if workflow_override:
                    WorkflowSetting.objects.create(
                        project=self.other_project,
                        language=second.translation.language,
                        translation_review=False,
                    )
                user.clear_permissions_cache()
                destination = Unit.objects.get(pk=second.pk)
                self.assertFalse(destination.translation.enable_review)
                self.assertFalse(user.has_perm("unit.review", destination))
                target = f"Approved {workflow_override}"
                # Disabling reviews can leave an existing approved state. Even
                # with identical text, it must not bypass the destination rules.
                Unit.objects.filter(pk=second.pk).update(
                    target=target, state=STATE_APPROVED, original_state=STATE_APPROVED
                )
                first.translate(user, target, STATE_APPROVED)
                second.refresh_from_db()
                self.assertEqual(second.state, STATE_TRANSLATED)
                self.assertEqual(second.original_state, STATE_TRANSLATED)
                self.assertEqual(second.target, first.target)

    def test_approval_fallback_skips_unchanged_translation(self) -> None:
        first, second, user, _reviewers = self.create_review_units()
        Unit.objects.filter(pk=second.pk).update(
            target="Same target", original_state=STATE_TRANSLATED
        )
        count = second.change_set.count()
        pending_count = PendingUnitChange.objects.filter(unit=second).count()
        first.translate(user, "Same target", STATE_APPROVED)
        second.refresh_from_db()
        self.assertEqual(second.state, STATE_TRANSLATED)
        self.assertEqual(second.original_state, STATE_TRANSLATED)
        self.assertEqual(second.change_set.count(), count)
        self.assertEqual(
            PendingUnitChange.objects.filter(unit=second).count(), pending_count
        )

    def test_approval_does_not_change_protected_destination(self) -> None:
        first, second, user, _reviewers = self.create_review_units()
        for state in (STATE_APPROVED, STATE_READONLY):
            with self.subTest(state=state):
                Unit.objects.filter(pk=second.pk).update(
                    state=state, original_state=state
                )
                user.clear_permissions_cache()
                self.assertFalse(
                    user.has_perm("unit.edit", Unit.objects.get(pk=second.pk))
                )
                first.translate(user, f"Approved {state}", STATE_APPROVED)
                second.refresh_from_db()
                self.assertEqual(second.target, "Second")
                self.assertEqual(second.state, state)
                self.assertFalse(
                    second.change_set.filter(
                        action=ActionEvents.PROPAGATED_EDIT
                    ).exists()
                )

    def test_approval_fallback_is_blocked_by_commit_policy(self) -> None:
        first, second, user, _reviewers = self.create_review_units()
        Project.objects.filter(pk=self.other_project.pk).update(
            commit_policy=CommitPolicyChoices.APPROVED_ONLY
        )
        first.translate(user, "Approved source", STATE_APPROVED)
        second = Unit.objects.get(pk=second.pk)
        self.assertTrue(second.is_blocked_by_commit_policy)
        pending = PendingUnitChange.objects.get(unit=second, target=first.target)
        self.assertEqual(pending.state, STATE_TRANSLATED)
        self.assertFalse(
            PendingUnitChange.objects.for_translation(second.translation)
            .filter(pk=pending.pk)
            .exists()
        )
        second.translation.commit_pending("test", user)
        self.assertTrue(PendingUnitChange.objects.filter(pk=pending.pk).exists())

    def test_project_propagation_also_checks_destination_review_permission(
        self,
    ) -> None:
        first, second, user, reviewers = self.create_review_units()
        self.set_scope("project")
        Component.objects.filter(pk=self.other.pk).update(
            project=self.project, name="Other component"
        )
        reviewers.components.add(self.component)
        user.clear_permissions_cache()
        self.assertFalse(user.has_perm("unit.review", Unit.objects.get(pk=second.pk)))
        first.translate(user, "Approved source", STATE_APPROVED)
        second.refresh_from_db()
        self.assertEqual(second.target, first.target)
        self.assertEqual(second.state, STATE_TRANSLATED)
