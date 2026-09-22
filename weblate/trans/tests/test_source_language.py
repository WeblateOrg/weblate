# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, PropertyMock, patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from weblate.api.serializers import UnitSerializer
from weblate.checks.ai import evaluation_fingerprint
from weblate.checks.chars import BeginSpaceCheck, EndSpaceCheck
from weblate.checks.consistency import ConsistencyCheck, ReusedCheck
from weblate.checks.format import JavaMessageFormatCheck
from weblate.formats.base import UnitNotFoundError
from weblate.glossary.forms import TermForm
from weblate.glossary.models import iter_glossary_alternatives
from weblate.lang.models import Language, Plural
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.llm import BaseLLMTranslation
from weblate.machinery.microsoft import MicrosoftCognitiveTranslation
from weblate.machinery.types import SourceLanguageChoices
from weblate.machinery.weblatetm import WeblateTranslation
from weblate.memory.models import Memory
from weblate.memory.tasks import (
    get_memory_status,
    get_unit_memory_update,
    import_memory,
)
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.bulk import bulk_perform
from weblate.trans.change_display import ShowChangeContent, ShowChangeSource
from weblate.trans.formatting import format_unit_source, get_source_changes
from weblate.trans.forms import MergeForm, TranslationForm, WorkflowSettingForm
from weblate.trans.models import (
    Comment,
    Component,
    PendingUnitChange,
    Project,
    Suggestion,
    Translation,
    Unit,
    WorkflowSetting,
)
from weblate.trans.models.project import CommitPolicyChoices
from weblate.trans.models.source import (
    DependencyWork,
    reconcile_component_parents,
    request_reconciliation,
    source_operation,
)
from weblate.trans.tests.test_views import FixtureComponentTestCase, ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin
from weblate.trans.util import join_plural
from weblate.trans.views.edit import get_addable_glossaries, get_other_units
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from django import forms

    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.memory.tasks import MemoryUpdatePayload


class SourceLanguageTest(FixtureComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.child = self.get_unit("Hello, world!\n", "cs")
        self.parent = self.get_unit("Hello, world!\n", "de")
        self.grandchild = self.get_unit("Hello, world!\n", "it")

    def configure(
        self, child: Unit | None = None, parent: Unit | None = None
    ) -> WorkflowSetting:
        return WorkflowSetting.objects.create(
            project=self.project,
            language=(child or self.child).translation.language,
            source_language=(parent or self.parent).translation.language,
        )

    def set_target(
        self, unit: Unit, target: str, state: int = STATE_TRANSLATED
    ) -> None:
        unit.refresh_from_db()
        unit.target = target
        unit.state = unit.original_state = state
        unit.save()

    def test_regular_operations_do_not_query_dependencies(self) -> None:
        self.assertFalse(self.component.project.translation_parent_language_ids)
        self.child.translation.component = self.component
        with self.assertNumQueries(0), source_operation(self.component):
            pass
        # The ordinary save retains its UPDATE and existing add-on lookup.
        with self.assertNumQueries(2):
            self.child.save(same_content=True, run_checks=False, sync_terminology=False)
        self.assertNotIn("translation_parent", self.child.details)

    def test_source_operation_coalesces_parent_edits(self) -> None:
        self.set_target(self.parent, "Original")
        self.configure()
        self.set_target(self.child, "Child")
        changes = self.child.change_set.filter(
            action=ActionEvents.SOURCE_CHANGE
        ).count()
        with source_operation(self.component):
            self.set_target(self.parent, "Intermediate")
            self.set_target(self.parent, "Final")
        self.child.refresh_from_db()
        self.assertEqual(
            self.child.details["translation_parent"]["applied"]["text"], "Final"
        )
        self.assertEqual(
            self.child.change_set.filter(action=ActionEvents.SOURCE_CHANGE).count(),
            changes + 1,
        )
        self.assertFalse(self.child.change_set.filter(target="Intermediate").exists())

    def test_reconciliation_is_idempotent(self) -> None:
        self.set_target(self.parent, "Parent")
        self.configure()
        self.set_target(self.child, "Child")
        with CaptureQueriesContext(connection) as queries:
            reconcile_component_parents(self.component)
            reconcile_component_parents(self.component)
        writes = [
            query["sql"]
            for query in queries
            if query["sql"].startswith(("UPDATE", "INSERT", "DELETE"))
        ]
        self.assertEqual(writes, [])

    def test_repeated_parent_changes_preserve_original_source(self) -> None:
        self.set_target(self.parent, "Original")
        self.configure()
        self.set_target(self.child, "Child")
        self.set_target(self.parent, "Second")
        self.set_target(self.parent, "Third")
        self.child.refresh_from_db()
        metadata = self.child.details["translation_parent"]
        self.assertEqual(metadata["previous"]["text"], "Original")
        self.assertEqual(metadata["applied"]["text"], "Third")
        self.set_target(self.parent, "Original")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_TRANSLATED)
        self.assertNotIn("previous", self.child.details["translation_parent"])
        self.assertEqual(
            self.child.details["translation_parent"]["applied"]["text"], "Original"
        )

    def test_source_operation_batches_deletion(self) -> None:
        self.set_target(self.parent, "Parent")
        self.configure()
        self.set_target(self.child, "Child")
        with source_operation(self.component):
            self.parent.delete()
            self.child.refresh_from_db()
            self.assertEqual(self.child.state, STATE_TRANSLATED)
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(self.child.effective_previous_source, "Parent")

    def test_source_operation_rollbacks(self) -> None:
        self.set_target(self.parent, "Original")
        self.configure()
        self.set_target(self.child, "Child")
        with source_operation(self.component):
            self.set_target(self.parent, "Final")
            with (
                self.assertRaisesMessage(ValueError, "Rollback"),
                source_operation(self.component),
            ):
                self.set_target(self.parent, "Discarded")
                request_reconciliation(self.component, DependencyWork(full=True))
                msg = "Rollback"
                raise ValueError(msg)
            self.child.refresh_from_db()
            self.assertEqual(self.child.state, STATE_TRANSLATED)
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(
            self.child.details["translation_parent"]["applied"]["text"], "Final"
        )
        self.assertFalse(self.child.change_set.filter(target="Discarded").exists())
        changes = self.child.change_set.count()
        with (
            self.assertRaisesMessage(ValueError, "Rollback"),
            source_operation(self.component),
        ):
            self.set_target(self.parent, "Discarded again")
            msg = "Rollback"
            raise ValueError(msg)
        self.assertEqual(self.child.change_set.count(), changes)
        self.set_target(self.parent, "Original")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_TRANSLATED)

    def test_plural_snapshot_survives_in_place_change(self) -> None:
        self.set_target(self.parent, "Parent")
        self.configure()
        self.set_target(self.child, "Child")
        old_formula = self.parent.translation.plural.formula
        Plural.objects.filter(pk=self.parent.translation.plural_id).update(
            formula="n > 1"
        )
        reconcile_component_parents(self.component)
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        metadata = self.child.details["translation_parent"]
        self.assertEqual(metadata["previous"]["formula"], old_formula)
        self.assertEqual(metadata["applied"]["formula"], "n > 1")
        change = self.child.change_set.filter(action=ActionEvents.SOURCE_CHANGE).latest(
            "pk"
        )
        with patch(
            "weblate.trans.change_display.format_unit_source", wraps=format_unit_source
        ) as render:
            ShowChangeSource(change).get_change_details_fields()
        self.assertEqual(len(render.call_args_list), 2)
        self.assertEqual(render.call_args_list[0].kwargs["plural"].formula, old_formula)
        self.assertEqual(render.call_args_list[1].kwargs["plural"].formula, "n > 1")

    def test_deletion_dependency_lookups_are_batched(self) -> None:
        units = Unit.objects.bulk_create(
            [
                Unit(
                    translation=self.child.translation,
                    source_unit=self.child.source_unit,
                    id_hash=1000000 + index,
                    position=index,
                    source=f"Bulk {index}",
                    target="",
                )
                for index in range(20)
            ]
        )
        queryset = Unit.objects.filter(pk__in=[unit.pk for unit in units])
        with CaptureQueriesContext(connection) as queries:
            queryset.delete()
        dependency_queries = [
            query["sql"]
            for query in queries
            if query["sql"].startswith("SELECT")
            and 'FROM "trans_unit"' in query["sql"]
            and "translation_parent_id" in query["sql"]
        ]
        self.assertLessEqual(len(dependency_queries), 3, dependency_queries)
        self.assertNotIn("_translation_children_delete_cache", queryset.__dict__)

    def test_source_ordering_uses_parent_text(self) -> None:
        regular = self.child.translation.unit_set.order_by_request(
            {"sort_by": "source"}, self.child.translation
        )
        self.assertNotIn("COALESCE", str(regular.query).upper())
        self.assertNotIn('JOIN "trans_unit"', str(regular.query))
        other = self.child.translation.unit_set.exclude(pk=self.child.pk).first()
        assert other is not None
        other_parent = self.parent.translation.unit_set.get(id_hash=other.id_hash)
        self.set_target(self.parent, "Zulu")
        self.set_target(other_parent, "Alpha")
        self.configure()
        units = Unit.objects.filter(pk__in=[self.child.pk, other.pk])
        for scope in (self.project, self.component, self.child.translation, None):
            for sort_by, expected in (
                ("source", [other.pk, self.child.pk]),
                ("-source", [self.child.pk, other.pk]),
            ):
                with self.subTest(scope=scope, sort_by=sort_by):
                    ordered = units.order_by_request({"sort_by": sort_by}, scope)
                    self.assertEqual(
                        list(ordered.values_list("pk", flat=True)), expected
                    )

    def test_disable_workflow_without_source_field(self) -> None:
        self.set_target(self.parent, "Parent source")
        workflow = self.configure()
        self.assertTrue(self.project.translation_parent_language_ids)
        form = WorkflowSettingForm(
            {"workflow-enable": "", "workflow-suggestion_autoaccept": "0"},
            instance=workflow,
            project=self.project,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.instance.source_language_id)
        form.save()
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.effective_source, self.child.source)
        self.assertFalse(self.project.translation_parent_language_ids)

    def test_memory_accepts_nonempty_effective_source(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        self.set_target(self.child, "Child translation")
        self.child.source = ""
        with patch("weblate.trans.models.unit.schedule_memory_update") as schedule:
            self.child.update_translation_memory(self.user, needs_user_check=False)
        payload = schedule.call_args.args[0]
        self.assertEqual(payload["source"], "Parent source")
        self.assertEqual(
            payload["source_language_id"], self.parent.translation.language_id
        )

    def test_parent_plural_invalidates_ai_fingerprint(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        self.set_target(self.child, "Child translation")
        fingerprint = evaluation_fingerprint(self.child)
        self.child.check_set.create(
            name="ai_accuracy",
            metadata={
                "fingerprint": fingerprint,
                "issues": [{"severity": "minor", "explanation": "Old plural issue"}],
            },
        )
        plural = Plural.objects.create(
            language=self.parent.translation.language,
            source=Plural.SOURCE_GETTEXT,
            number=2,
            formula="n > 1",
        )
        Translation.objects.filter(pk=self.parent.translation_id).update(plural=plural)
        self.child = Unit.objects.get(pk=self.child.pk)
        self.assertNotEqual(evaluation_fingerprint(self.child), fingerprint)
        self.child.invalidate_checks_cache()
        self.child.run_checks()
        self.assertFalse(self.child.check_set.filter(name="ai_accuracy").exists())

    def test_identical_text_parent_language_change_invalidates_child(self) -> None:
        self.set_target(self.parent, "Gift")
        self.set_target(self.grandchild, "Gift")
        workflow = self.configure()
        self.set_target(self.child, "Translation", STATE_APPROVED)
        workflow.source_language = self.grandchild.translation.language
        workflow.save()
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(self.child.effective_previous_source, "Gift")
        change = self.child.change_set.filter(action=ActionEvents.SOURCE_CHANGE).latest(
            "pk"
        )
        self.assertEqual(
            change.details["previous_source_snapshot"]["language_id"],
            self.parent.translation.language_id,
        )
        workflow.source_language = self.parent.translation.language
        workflow.save()
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_TRANSLATED)

    def test_source_comment_search_includes_parent(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        comment = Comment.objects.create(
            unit=self.parent, user=self.user, comment="Parent issue"
        )
        units = Unit.objects.filter(pk=self.child.pk)
        for resolved in (False, True):
            comment.resolved = resolved
            comment.save()
            prefix = "resolved_" if resolved else ""
            for query in (
                f"{prefix}source_comment:issue",
                f"has:{prefix}source_comment",
                f"source_comment_author:{self.user.username}",
            ):
                with self.subTest(query=query):
                    self.assertTrue(units.search(query, project=self.project).exists())
            opposite = "" if resolved else "resolved_"
            self.assertFalse(
                units.search(
                    f"{opposite}source_comment:issue", project=self.project
                ).exists()
            )
        Comment.objects.create(
            unit=self.child.source_unit, user=self.user, comment="Canonical issue"
        )
        self.assertTrue(
            units.search("source_comment:Canonical", project=self.project).exists()
        )

    def test_glossary_search_matches_parent(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        with patch.object(
            Project,
            "glossaries",
            PropertyMock(return_value=[Mock(glossary_sources={"Hallo"})]),
        ):
            self.assertTrue(
                Unit.objects.filter(pk=self.child.pk)
                .search("has:glossary", project=self.project)
                .exists()
            )
            self.assertFalse(
                Unit.objects.filter(pk=self.child.pk)
                .search("NOT has:glossary", project=self.project)
                .exists()
            )

    def test_report_preserves_blocked_parent_invalidation(self) -> None:
        self.set_target(self.parent, "Parent")
        self.configure()
        self.set_target(self.child, "Child")
        self.configure(self.grandchild, self.child)
        self.set_target(self.grandchild, "Grandchild")
        self.set_target(self.parent, "Parent", STATE_NEEDS_REWRITING)
        self.grandchild.refresh_from_db()
        Comment.objects.add(
            cast("AuthenticatedHttpRequest", RequestFactory().post("/")),
            self.grandchild,
            "Reported middle source",
            "report",
            user=self.user,
        )
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)
        self.assertEqual(self.child.original_state, STATE_NEEDS_REWRITING)
        self.set_target(self.parent, "Parent", STATE_TRANSLATED)
        self.child.refresh_from_db()
        self.grandchild.refresh_from_db()
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(self.grandchild.state, STATE_READONLY)

    def test_regular_project_uses_canonical_lookup_queries(self) -> None:
        self.child.target = "Translation"
        for queryset in (
            Unit.objects.same(self.child),
            Unit.objects.same_target(self.child),
        ):
            sql = str(queryset.query).upper()
            self.assertNotIn("COALESCE(", sql)
            self.assertNotIn('LEFT OUTER JOIN "TRANS_UNIT"', sql)
            self.assertNotIn("'BLOCKED'", sql)
        search_units = self.child.translation.unit_set.search(
            "source:hello", project=self.project
        )
        self.assertNotIn(
            'LEFT OUTER JOIN "TRANS_UNIT"', str(search_units.query).upper()
        )
        with CaptureQueriesContext(connection) as queries:
            get_other_units(self.user, self.child)
        lookup_sql = next(
            query["sql"].upper()
            for query in queries
            if 'FROM "TRANS_UNIT"' in query["sql"].upper()
            and "CASE WHEN" in query["sql"].upper()
        )
        self.assertNotIn("COALESCE(", lookup_sql)
        self.assertNotIn('LEFT OUTER JOIN "TRANS_UNIT"', lookup_sql)
        self.assertIn('MD5(LOWER("TRANS_UNIT"."SOURCE"))', lookup_sql)
        with CaptureQueriesContext(connection) as queries:
            list(ReusedCheck().check_component(self.component))
        for query in queries:
            self.assertNotIn("COALESCE(", query["sql"].upper())
            self.assertNotIn("'blocked'", query["sql"])

    def test_workflow_changes_invalidate_live_project_source_cache(self) -> None:
        other = Project.objects.get(pk=self.project.pk)
        self.assertEqual(other.translation_parent_language_ids, set())
        workflow = self.configure()
        self.assertEqual(
            other.translation_parent_language_ids, {self.parent.translation.language_id}
        )
        with self.assertNumQueries(0):
            self.assertEqual(
                other.translation_parent_language_ids,
                {self.parent.translation.language_id},
            )
        workflow.delete()
        self.assertEqual(other.translation_parent_language_ids, set())

    def test_canonical_unit_keeps_custom_project_lookup(self) -> None:
        self.configure()
        self.parent.refresh_from_db()
        self.assertIsNone(self.parent.translation_parent_id)
        self.assertIn(
            'LEFT OUTER JOIN "TRANS_UNIT"',
            str(Unit.objects.same(self.parent).query).upper(),
        )

    def test_failed_parent_save_blocks_descendants(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        self.set_target(self.child, "Child source")
        self.configure(self.grandchild, self.child)
        for missing in (False, True):
            with self.subTest(missing=missing):
                self.set_target(self.parent, "Parent source")
                PendingUnitChange.store_unit_change(unit=self.parent, author=None)
                pending = PendingUnitChange.objects.filter(unit=self.parent).latest(
                    "pk"
                )
                # A queued older edit must not replace the current effective source.
                pending.target = "Earlier parent source"
                if missing:
                    store = Mock()
                    store.find_unit.side_effect = UnitNotFoundError
                    self.parent.translation.update_units([pending], store, "Test")
                else:
                    self.parent.translation._store_failed_unit_update(  # ruff: ignore[private-member-access]
                        self.parent, pending, ValueError("Cannot save")
                    )
                for unit in (self.child, self.grandchild):
                    unit.refresh_from_db()
                    self.assertEqual(unit.state, STATE_READONLY)
                    self.assertTrue(unit.translation_parent_blocked)
                self.assertEqual(self.child.effective_source, "Parent source")

    def test_bulk_parent_state_blocks_descendants(self) -> None:
        self.set_target(self.parent, "Parent")
        self.set_target(self.child, "Child")
        self.set_target(self.grandchild, "Grandchild")
        self.configure()
        self.configure(self.grandchild, self.child)
        self.set_target(self.child, "Child")
        self.set_target(self.grandchild, "Grandchild")
        for state in (STATE_NEEDS_REWRITING, STATE_TRANSLATED):
            with self.subTest(state=state):
                bulk_perform(
                    None,
                    Unit.objects.filter(pk=self.parent.pk),
                    query="",
                    target_state=state,
                    add_flags="",
                    remove_flags="",
                    add_labels=self.project.label_set.none(),
                    remove_labels=self.project.label_set.none(),
                    project=self.project,
                )
                for unit in (self.child, self.grandchild):
                    unit.refresh_from_db()
                    self.assertEqual(
                        unit.translation_parent_blocked, state == STATE_NEEDS_REWRITING
                    )
                    self.assertEqual(
                        unit.state,
                        STATE_READONLY
                        if state == STATE_NEEDS_REWRITING
                        else STATE_TRANSLATED,
                    )

    def test_internal_machinery_matches_parent(self) -> None:
        self.set_target(self.parent, "Long German source")
        self.configure()
        self.set_target(self.child, "Czech translation")
        machine = WeblateTranslation({})
        for text in (
            "Long German source",
            "app",
            join_plural(["Long German source", "app"]),
        ):
            if "app" in text:
                self.component.file_format = "csv-multi"
                Component.objects.filter(pk=self.component.pk).update(
                    file_format="csv-multi"
                )
            self.set_target(self.parent, text)
            self.child.refresh_from_db()
            self.set_target(self.child, "Czech translation")
            for threshold in (100, 75):
                with self.subTest(text=text, threshold=threshold):
                    results = list(
                        machine.download_translations(
                            self.parent.translation.language,
                            self.child.translation.language,
                            "app" if "app" in text else text,
                            None,
                            self.user,
                            threshold,
                        )
                    )
                    self.assertIn(
                        "Czech translation", {result["text"] for result in results}
                    )
        self.set_target(self.parent, "app", STATE_NEEDS_REWRITING)
        self.assertEqual(
            list(
                machine.download_translations(
                    self.parent.translation.language,
                    self.child.translation.language,
                    "app",
                    None,
                    self.user,
                    100,
                )
            ),
            [],
        )

    def test_effective_source_alternatives_preserve_unit(self) -> None:
        self.set_target(self.child, join_plural(["One", "Few", "Many"]))
        self.configure(self.grandchild, self.child)
        self.set_target(self.grandchild, join_plural(["Uno", "Molti"]))
        unit = Unit.objects.get(pk=self.grandchild.pk)
        source = unit.source
        alternatives = list(iter_glossary_alternatives([unit], effective_source=True))
        pairs = [(item.source, item.target) for item in alternatives]
        self.assertEqual(pairs, [("One", "Uno"), ("Many", "Molti")])
        entries = [
            BaseLLMTranslation._get_glossary_entry(item)  # ruff: ignore[private-member-access]
            for item in alternatives
        ]
        self.assertEqual(
            entries,
            [{"source": "One", "target": "Uno"}, {"source": "Many", "target": "Molti"}],
        )
        self.assertEqual(unit.source, source)
        Component.objects.filter(pk=self.component.pk).update(file_format="csv-multi")
        machine = WeblateTranslation({})
        for form in ("One", "Few", "Many"):
            with self.subTest(form=form):
                results = list(
                    machine.download_translations(
                        self.child.translation.language,
                        self.grandchild.translation.language,
                        form,
                        None,
                        self.user,
                        100,
                    )
                )
                self.assertEqual(
                    {result["text"] for result in results}, {"Uno", "Molti"}
                )
                self.assertEqual({result["source"] for result in results}, {form})

    def test_tm_candidates_preload_complete_source(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        self.set_target(self.child, "Child translation")
        machine = WeblateTranslation({})
        units = list(machine.prepare_queryset(Unit.objects.filter(pk=self.child.pk)))
        with self.assertNumQueries(0):
            for unit in units:
                self.assertEqual(unit.source_snapshot.text, "Parent source")
                self.assertEqual(unit.source_snapshot.language_code, "de")
                self.assertEqual(unit.source_snapshot.number, 2)

    def test_effective_source_text_does_not_load_metadata(self) -> None:
        unit = Unit.objects.get(pk=self.child.pk)
        with self.assertNumQueries(0):
            self.assertEqual(unit.effective_source_string, unit.source_string)
            self.assertEqual(
                unit.get_effective_source_plurals(), unit.get_source_plurals()
            )
            self.assertEqual(unit.edit_content_hash, unit.content_hash)
        self.set_target(self.parent, "Parent source")
        self.configure()
        unit = Unit.objects.select_related("translation_parent").get(pk=self.child.pk)
        with self.assertNumQueries(0):
            self.assertEqual(unit.effective_source_string, "Parent source")
            self.assertEqual(unit.get_effective_source_plurals(), ["Parent source"])

    def test_microsoft_glossary_matches_parent_alternatives(self) -> None:
        self.component.file_format = "csv-multi"
        Component.objects.filter(pk=self.component.pk).update(file_format="csv-multi")
        self.set_target(self.parent, join_plural(["Another alias", self.child.source]))
        self.configure()
        self.child.refresh_from_db()
        term = Mock(
            source=self.child.source.strip(),
            target="Term translation",
            all_flags=set(),
            glossary_positions=((14, 27),),
        )
        machine = MicrosoftCognitiveTranslation(
            {"key": "test", "region": "", "endpoint_url": "api.cognitive.microsoft.com"}
        )
        with (
            patch("weblate.machinery.microsoft.get_glossary_terms", return_value=[]),
            patch(
                "weblate.machinery.microsoft.iter_glossary_alternatives",
                return_value=[term],
            ),
        ):
            highlights = list(machine.get_highlights(self.child.source, self.child))
        self.assertIn((0, len(term.source), term.source, term), highlights)
        assert self.child.translation_parent is not None
        self.child.translation_parent.translation.language = Language.objects.get(
            code="zh_Hans"
        )
        self.child.translation_parent.target = join_plural(
            ["Another alias", "application"]
        )
        term.source = "app"
        with (
            patch("weblate.machinery.microsoft.get_glossary_terms", return_value=[]),
            patch(
                "weblate.machinery.microsoft.iter_glossary_alternatives",
                return_value=[term],
            ),
        ):
            highlights = list(machine.get_highlights("application", self.child))
        self.assertIn((0, 3, "app", term), highlights)

    def test_workload_follows_parent(self) -> None:
        canonical_words = self.child.num_words
        self.set_target(self.parent, "A much longer source with seven words")
        workflow = self.configure()
        self.child.refresh_from_db()
        self.assertEqual(self.child.num_words, 7)
        data = UnitSerializer(
            self.child, context={"request": RequestFactory().get("/")}
        ).data
        self.assertEqual(data["num_words"], 7)
        self.child.translation.stats.update_stats()
        words = self.child.translation.stats.all_words
        chars = self.child.translation.stats.all_chars
        self.assertEqual(
            chars,
            sum(
                len(unit.effective_source)
                for unit in self.child.translation.unit_set.all()
            ),
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.set_target(self.parent, "Kurz")
        self.child.refresh_from_db()
        self.assertEqual(self.child.translation.stats.all_words, words - 6)
        self.assertEqual(
            self.child.translation.stats.all_chars,
            chars - len("A much longer source with seven words") + 4,
        )
        self.assertEqual(
            self.child.translation.stats.capture_unit_snapshot(
                Unit.objects.prefetch().prefetch_full().get(pk=self.child.pk)
            )["num_chars"],
            4,
        )
        self.set_target(self.parent, "Kurz")
        self.child.refresh_from_db()
        self.assertEqual(self.child.num_words, 1)
        self.child.save()
        self.child.refresh_from_db()
        self.assertEqual(self.child.num_words, 1)
        workflow.delete()
        self.child.refresh_from_db()
        self.assertEqual(self.child.num_words, canonical_words)

    def test_cross_unit_checks_use_effective_source(self) -> None:
        other = self.child.translation.unit_set.exclude(pk=self.child.pk).first()
        assert other is not None
        parent = self.parent.translation.unit_set.get(id_hash=other.id_hash)
        self.set_target(self.parent, "Gemeinsamer Ausgangstext")
        self.set_target(parent, self.parent.target)
        self.configure()
        self.set_target(self.child, "Shared translation")
        self.set_target(other, "Shared translation")
        other.context = self.child.context
        other.save()
        reused = ReusedCheck()
        inconsistent = ConsistencyCheck()
        self.assertFalse(Unit.objects.same_target(self.child).exists())
        self.assertNotIn(self.child, list(reused.check_component(self.component)))
        self.assertIn(other, self.child.propagated_units)
        self.set_target(other, "Another translation")
        self.assertIn(self.child, list(inconsistent.check_component(self.component)))
        self.set_target(parent, "Anderer Ausgangstext")
        self.set_target(other, "Shared translation")
        self.assertIn(other, Unit.objects.same_target(self.child))
        self.assertIn(self.child, list(reused.check_component(self.component)))
        # Canonical text equality must not hide different effective sources.
        other.source = self.child.source
        other.save()
        self.assertIn(other, Unit.objects.same_target(self.child))
        self.assertIn(self.child, list(reused.check_component(self.component)))
        self.assertNotIn(self.child, list(inconsistent.check_component(self.component)))
        self.child.invalidate_checks_cache()
        self.child.run_checks()
        self.assertTrue(self.child.check_set.filter(name="reused").exists())
        self.set_target(parent, self.parent.target)
        self.assertFalse(self.child.check_set.filter(name="reused").exists())
        # Identical text in another source language does not establish equivalence.
        self.set_target(self.grandchild, self.parent.target)
        other.translation_parent = self.grandchild
        other.save(only_save=True)
        self.assertNotIn(other, Unit.objects.same(self.child))
        self.assertNotIn(other, Unit.objects.same_target(self.child))
        self.assertNotIn(self.child, list(reused.check_component(self.component)))

    def test_custom_source_consistency_global_limit(self) -> None:
        self.set_target(self.parent, "Effective source")
        self.configure()
        self.configure(self.grandchild, self.parent)
        translations = (self.child.translation, self.grandchild.translation)
        units: list[Unit] = []
        for index in range(101):
            for translation in translations:
                for variant, target in enumerate(("First", "Second")):
                    units.append(
                        Unit(
                            translation=translation,
                            source_unit=self.child.source_unit,
                            translation_parent=self.parent,
                            id_hash=-1000 - len(units),
                            position=1000 + len(units),
                            source=f"Canonical source {index}/{variant}",
                            context=f"Group {index:03d}",
                            target=target,
                            state=STATE_TRANSLATED,
                        )
                    )
        Unit.objects.bulk_create(units)
        expected: dict[tuple[str, int], set[int]] = defaultdict(set)
        for unit in units:
            expected[unit.context, unit.translation.plural_id].add(unit.pk)
        expected_ids = set().union(*(expected[key] for key in sorted(expected)[:100]))
        self.assertSetEqual(
            {unit.pk for unit in ConsistencyCheck().check_component(self.component)},
            expected_ids,
        )

    def test_blocked_units_do_not_affect_cross_unit_checks(self) -> None:
        other = self.child.translation.unit_set.exclude(pk=self.child.pk).first()
        assert other is not None
        other_parent = self.parent.translation.unit_set.get(id_hash=other.id_hash)
        self.set_target(self.parent, "Parent source")
        self.set_target(other_parent, "Parent source")
        self.configure()
        self.set_target(self.child, "Shared target")
        self.set_target(other, "Another target")
        other.context = self.child.context
        other.save(only_save=True)
        self.assertIn(self.child, Unit.objects.same(other))
        self.assertIn(other, list(ConsistencyCheck().check_component(self.component)))
        self.set_target(self.parent, self.parent.target, STATE_NEEDS_REWRITING)
        other.refresh_from_db()
        self.assertNotIn(self.child, Unit.objects.same(other))
        self.assertNotIn(
            other, list(ConsistencyCheck().check_component(self.component))
        )
        self.set_target(other_parent, "Different source")
        self.set_target(other, "Shared target")
        self.assertNotIn(self.child, Unit.objects.same_target(other))
        self.assertNotIn(other, list(ReusedCheck().check_component(self.component)))

    def test_multivalue_parent_is_excluded_from_memory(self) -> None:
        self.set_target(self.parent, join_plural(["First", "Second"]))
        self.configure()
        self.set_target(self.child, "Translation")
        with patch.object(
            Component, "is_multivalue", new_callable=PropertyMock, return_value=True
        ):
            self.assertTrue(self.child.is_multivalue)
            self.assertIsNone(get_unit_memory_update(self.child))

    def test_java_format_detection_uses_parent(self) -> None:
        self.child.extra_flags = "auto-java-messageformat"
        self.child.save(update_fields=["extra_flags"])
        self.set_target(self.parent, "Hello {0}")
        self.configure()
        self.set_target(self.child, "Hello")
        check = JavaMessageFormatCheck()
        self.assertFalse(check.should_skip(self.child))
        self.assertTrue(
            check.check_target_unit(
                [self.parent.target], [self.child.target], self.child
            )
        )
        self.set_target(self.parent, "Hello")
        self.child.refresh_from_db()
        self.child.source = "Canonical {0}"
        self.child.invalidate_checks_cache()
        self.assertTrue(check.should_skip(self.child))

    def test_parent_switch_preserves_both_plural_rules_in_history(self) -> None:
        self.set_target(self.parent, join_plural(["German one", "German many"]))
        self.set_target(
            self.child, join_plural(["Czech one", "Czech few", "Czech many"])
        )
        workflow = self.configure(self.grandchild, self.parent)
        workflow.source_language = self.child.translation.language
        workflow.save()
        change = self.grandchild.change_set.filter(
            action=ActionEvents.SOURCE_CHANGE
        ).latest("pk")
        with patch(
            "weblate.trans.change_display.format_unit_source", wraps=format_unit_source
        ) as render:
            ShowChangeSource(change).get_change_details_fields()
        self.assertEqual(len(render.call_args_list), 2)
        previous, current = (call.kwargs for call in render.call_args_list)
        self.assertEqual(previous["value"], self.parent.target)
        self.assertEqual(previous["language"], self.parent.translation.language)
        self.assertEqual(previous["plural"], self.parent.translation.plural)
        self.assertEqual(current["value"], self.child.target)
        self.assertEqual(current["language"], self.child.translation.language)
        self.assertEqual(current["plural"], self.child.translation.plural)
        self.assertIsNone(current["diff"])

    def test_editor_preserves_previous_plural_metadata(self) -> None:
        self.set_target(
            self.child, join_plural(["Czech one", "Czech few", "Czech many"])
        )
        self.set_target(self.parent, join_plural(["German one", "German many"]))
        workflow = self.configure(self.grandchild, self.child)
        self.set_target(self.grandchild, "Italian translation")
        workflow.source_language = self.parent.translation.language
        workflow.save()
        self.grandchild.refresh_from_db()
        changes = get_source_changes(self.grandchild)
        self.assertEqual(len(changes), 2)
        previous, current = changes[0], changes[1]
        self.assertEqual(previous["language"], self.child.translation.language)
        self.assertEqual(previous["plural"], self.child.translation.plural)
        self.assertEqual(previous["value"], self.child.target)
        self.assertEqual(current["language"], self.parent.translation.language)
        self.assertEqual(current["plural"], self.parent.translation.plural)
        self.assertIsNone(current["diff"])
        rendered = format_unit_source(
            self.grandchild,
            **{key: value for key, value in previous.items() if key != "label"},
        )
        self.assertIn("Czech many", str(rendered))
        # Another parent edit must retain metadata belonging to the original diff.
        self.set_target(self.parent, "Updated German source")
        self.grandchild.refresh_from_db()
        self.assertEqual(get_source_changes(self.grandchild)[0], previous)

    def test_editor_merges_match_effective_sources(self) -> None:
        other = self.child.translation.unit_set.exclude(pk=self.child.pk).first()
        assert other is not None
        parent = self.parent.translation.unit_set.get(id_hash=other.id_hash)
        self.set_target(self.parent, "Shared source")
        self.set_target(parent, "Shared source")
        self.configure()
        self.set_target(self.child, "Translation")
        self.set_target(other, "Different translation")
        other.context = self.child.context
        other.save(only_save=True)
        candidates = get_other_units(self.user, self.child)
        self.assertIn(other, candidates["matching"])
        form = MergeForm(self.user, self.child, {"merge": other.pk})
        self.assertTrue(form.is_valid(), form.errors)
        self.set_target(parent, parent.target, STATE_NEEDS_REWRITING)
        self.assertFalse(
            MergeForm(self.user, self.child, {"merge": other.pk}).is_valid()
        )
        self.set_target(parent, parent.target)
        self.set_target(parent, "Changed source")
        self.set_target(other, "Different translation")
        other.source = self.child.source
        other.save(only_save=True)
        self.assertNotIn(other, get_other_units(self.user, self.child)["matching"])
        self.assertFalse(
            MergeForm(self.user, self.child, {"merge": other.pk}).is_valid()
        )

        self.set_target(self.grandchild, self.parent.target)
        other.translation_parent = self.grandchild
        other.save(only_save=True)
        self.assertNotIn(other, get_other_units(self.user, self.child)["matching"])
        self.assertFalse(
            MergeForm(self.user, self.child, {"merge": other.pk}).is_valid()
        )

    def test_add_term_requires_effective_source_language(self) -> None:
        self.set_target(self.parent, "German source")
        self.configure()
        self.child.refresh_from_db()
        Component.objects.filter(pk=self.component.pk).update(manage_units=True)
        glossaries = Translation.objects.filter(pk=self.child.translation_id)
        data = {
            "translation": self.child.translation_id,
            "source": "German",
            "target": "Czech",
        }
        with patch.object(Translation, "get_glossaries", return_value=glossaries):
            self.assertEqual(get_addable_glossaries(self.child, self.user), ([], []))
        form = TermForm(
            self.child, self.user, data, glossaries=glossaries, filter_permissions=False
        )
        self.assertFalse(form.is_valid())
        self.assertIn("translation", form.errors)
        Component.objects.filter(pk=self.component.pk).update(
            source_language=self.parent.translation.language
        )
        with patch.object(Translation, "get_glossaries", return_value=glossaries):
            choices, _ = get_addable_glossaries(self.child, self.user)
            self.assertEqual(
                [choice.pk for choice in choices], [self.child.translation_id]
            )
        form = TermForm(
            self.child, self.user, glossaries=glossaries, filter_permissions=False
        )
        self.assertEqual(list(form.glossaries), [self.child.translation])

    def test_disabling_missing_parent_workflow_clears_snapshot(self) -> None:
        workflow = self.configure()
        self.parent.translation.delete()
        self.child = Unit.objects.get(pk=self.child.pk)
        self.set_target(self.child, "Accepted fallback")
        self.assertIn("applied", self.child.details["translation_parent"])
        workflow.delete()
        self.child.refresh_from_db()
        self.assertNotIn("translation_parent", self.child.details)

    def test_move_canonical_language_with_missing_parent(self) -> None:
        workflow = self.configure()
        self.parent.translation.delete()
        self.child = Unit.objects.get(pk=self.child.pk)
        self.set_target(self.child, "Translated fallback")
        old_language = self.child.effective_source_language
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(
            self.child.details["translation_parent"]["applied"]["language_id"],
            old_language.pk,
        )
        target = Language.objects.get(code="fr")
        Language.objects.move_language(old_language, target)
        self.child = Unit.objects.get(pk=self.child.pk)
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(self.child.effective_source_language, target)
        metadata = self.child.details["translation_parent"]
        self.assertEqual(metadata["previous"]["language_id"], old_language.pk)
        self.assertEqual(metadata["applied"]["language_id"], target.pk)
        workflow.refresh_from_db()
        self.assertEqual(
            workflow.source_language_id, self.parent.translation.language_id
        )

    def check_move_child_language(self, *, configured: bool) -> None:
        self.set_target(self.child, "Child translation")
        self.set_target(self.parent, "", STATE_EMPTY)
        self.configure()
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)
        target = Language.objects.auto_get_or_create("cs_CUSTOM")
        if configured:
            self.set_target(self.grandchild, "New source")
            WorkflowSetting.objects.create(
                project=self.project,
                language=target,
                source_language=self.grandchild.translation.language,
            )
        Language.objects.move_language(self.child.translation.language, target)
        child = Unit.objects.get(pk=self.child.pk)
        self.assertEqual(child.translation.language_id, target.pk)
        self.assertEqual(
            child.translation_parent_id, self.grandchild.pk if configured else None
        )
        self.assertFalse(child.translation_parent_blocked)
        self.assertEqual(
            child.state, STATE_NEEDS_REWRITING if configured else STATE_TRANSLATED
        )
        self.assertEqual(
            child.effective_source, "New source" if configured else child.source
        )
        if not configured:
            self.assertNotIn("translation_parent", child.details)

    def test_move_child_language_without_workflow(self) -> None:
        self.check_move_child_language(configured=False)

    def test_move_child_language_with_different_workflow(self) -> None:
        self.check_move_child_language(configured=True)

    def test_move_parent_language(self) -> None:
        self.set_target(self.parent, "Parent source")
        workflow = self.configure()
        target = Language.objects.get(code="fr")
        Language.objects.move_language(self.parent.translation.language, target)
        workflow.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(workflow.source_language_id, target.pk)
        self.assertEqual(self.child.effective_source_language, target)
        self.assertEqual(self.child.effective_source, "Parent source")

    def test_move_parent_language_to_existing_translation(self) -> None:
        self.set_target(self.parent, "German source")
        self.set_target(self.grandchild, "Italian source")
        workflow = self.configure()
        Language.objects.move_language(
            self.parent.translation.language, self.grandchild.translation.language
        )
        workflow.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(
            workflow.source_language_id, self.grandchild.translation.language_id
        )
        self.assertEqual(self.child.translation_parent_id, self.grandchild.pk)
        self.assertEqual(self.child.effective_source, "Italian source")

    def test_move_parent_language_to_child(self) -> None:
        self.set_target(self.parent, "Parent source")
        workflow = self.configure()
        Language.objects.move_language(
            self.parent.translation.language, self.child.translation.language
        )
        workflow.refresh_from_db()
        self.child.refresh_from_db()
        self.assertIsNone(workflow.source_language_id)
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.effective_source, self.child.source)

    def test_move_parent_language_rejects_cycle(self) -> None:
        self.configure()
        self.configure(self.grandchild, self.child)
        with self.assertRaises(ValidationError):
            Language.objects.move_language(
                self.parent.translation.language, self.grandchild.translation.language
            )
        self.parent.translation.refresh_from_db()
        self.assertEqual(self.parent.translation.language.code, "de")

    def test_automatic_translation_preloads_parents(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        translator = AutoTranslate(
            translation=self.child.translation, user=None, q="", mode="translate"
        )
        with patch("weblate.trans.autotranslate.fetch_machinery_matches") as fetch:
            translator.fetch_mt([], 80)
        units = fetch.call_args.kwargs["units"]
        self.assertTrue(units)
        with self.assertNumQueries(0):
            for unit in units:
                self.assertEqual(unit.effective_source_language.code, "de")
                unit.get_effective_source_plurals()
                self.assertEqual(unit.effective_source_plural.number, 2)

    def test_edit_conflict_detects_effective_source_changes(self) -> None:
        self.assertEqual(self.child.edit_content_hash, self.child.content_hash)
        self.set_target(self.parent, "Parent source")
        workflow = self.configure()
        self.set_target(self.child, "Child translation")
        canonical_hash = self.child.content_hash
        for change in ("text", "plural", "language", "detach"):
            with self.subTest(change=change):
                form = TranslationForm(self.user, self.child)
                data = {
                    "checksum": form.initial["checksum"],
                    "contentsum": form.initial["contentsum"],
                    "translationsum": form.initial["translationsum"],
                    "target_0": "Stale translation",
                    "review": str(STATE_TRANSLATED),
                }
                self.assertTrue(TranslationForm(self.user, self.child, data).is_valid())
                if change == "text":
                    self.set_target(self.parent, "Updated parent")
                elif change == "plural":
                    plural = self.parent.translation.plural
                    plural.formula = "n > 1"
                    plural.save()
                elif change == "language":
                    self.set_target(self.grandchild, self.parent.target)
                    workflow.source_language = self.grandchild.translation.language
                    workflow.save()
                else:
                    workflow.delete()
                self.child.refresh_from_db()
                self.assertEqual(self.child.content_hash, canonical_hash)
                form = TranslationForm(self.user, self.child, data)
                self.assertFalse(form.is_valid())
                self.assertIn(
                    "The source string has changed meanwhile.",
                    str(form.non_field_errors()),
                )

    def test_api_previous_effective_source(self) -> None:
        self.set_target(self.parent, "Old parent")
        self.configure()
        self.set_target(self.child, "Child translation")
        self.set_target(self.parent, "New parent")
        self.child.refresh_from_db()
        serializer = UnitSerializer(
            self.child, context={"request": RequestFactory().get("/")}
        )
        self.assertEqual(serializer.data["effective_previous_source"], ["Old parent"])
        self.assertEqual(serializer.data["effective_source"], ["New parent"])
        self.assertEqual(serializer.data["previous_source"], "")

    def test_canonical_source_and_api(self) -> None:
        source_id, source, identity = (
            self.child.source_unit_id,
            self.child.source,
            self.child.id_hash,
        )
        self.set_target(self.parent, "Hallo, Welt!")
        self.configure()
        self.child.refresh_from_db()
        self.assertEqual(self.child.source_unit_id, source_id)
        self.assertEqual(self.child.source, source)
        self.assertEqual(self.child.id_hash, identity)
        self.assertEqual(self.child.translation_parent_id, self.parent.pk)
        self.assertEqual(self.child.effective_source, self.parent.target)
        self.assertEqual(self.child.effective_source_language.code, "de")
        data = UnitSerializer(
            self.child, context={"request": RequestFactory().get("/")}
        ).data
        self.assertEqual(data["source"], [source])
        self.assertEqual(data["effective_source"], [self.parent.target])
        self.assertEqual(data["effective_source_language"], "de")
        self.assertTrue(data["source_unit"].endswith(f"/{source_id}/"))
        self.assertTrue(data["translation_parent"].endswith(f"/{self.parent.pk}/"))

    def test_parent_readiness(self) -> None:
        self.configure()
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)
        self.assertEqual(self.child.original_state, STATE_EMPTY)
        self.set_target(self.parent, "Hallo")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_EMPTY)
        self.set_target(self.parent, "Hallo", STATE_NEEDS_REWRITING)
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)
        self.set_target(self.parent, "Hallo", STATE_APPROVED)
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_EMPTY)

    def test_text_invalidation_and_revert(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        self.set_target(self.parent, "Guten Tag")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(self.child.target, "Ahoj")
        self.assertEqual(self.child.effective_previous_source, "Hallo")
        self.assertEqual(self.child.previous_source, "")
        self.set_target(self.parent, "Hallo")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_TRANSLATED)

    def test_descendant_readiness_without_text_change(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        self.configure(self.grandchild, self.child)
        self.set_target(self.grandchild, "Ciao")
        self.set_target(self.parent, "Guten Tag")
        self.grandchild.refresh_from_db()
        self.assertEqual(self.grandchild.state, STATE_READONLY)
        self.assertEqual(self.grandchild.effective_source, "Ahoj")
        self.assertEqual(self.grandchild.original_state, STATE_TRANSLATED)
        self.set_target(self.child, "Dobrý den")
        self.grandchild.refresh_from_db()
        self.assertEqual(self.grandchild.state, STATE_NEEDS_REWRITING)
        self.assertEqual(self.grandchild.effective_source, "Dobrý den")

    def test_parent_removal_preserves_children(self) -> None:
        self.set_target(self.parent, "Hallo")
        setting = self.configure()
        self.set_target(self.child, "Ahoj")
        Unit.objects.filter(pk=self.parent.pk).delete()
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.effective_source, self.child.source)
        self.assertEqual(self.child.target, "Ahoj")
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        setting.refresh_from_db()
        self.assertIsNotNone(setting.source_language_id)

    def test_missing_unit_and_later_creation(self) -> None:
        identity = self.parent.id_hash
        translation = self.parent.translation
        self.parent.delete()
        self.configure()
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        parent = Unit.objects.create(
            translation=translation,
            id_hash=identity,
            source_unit=self.child.source_unit,
            source=self.child.source,
            target="Hallo",
            state=STATE_TRANSLATED,
            original_state=STATE_TRANSLATED,
            position=1,
        )
        reconcile_component_parents(self.component)
        self.child.refresh_from_db()
        self.assertEqual(self.child.translation_parent_id, parent.pk)

    def test_remove_workflow(self) -> None:
        setting = self.configure()
        WorkflowSetting.objects.filter(pk=setting.pk).delete()
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.state, STATE_EMPTY)

    def test_validation(self) -> None:
        self.configure()
        for language, source, project in (
            (
                self.parent.translation.language,
                self.child.translation.language,
                self.project,
            ),
            (
                self.child.translation.language,
                self.child.translation.language,
                self.project,
            ),
            (
                self.child.translation.language,
                Language.objects.get(code="fr"),
                self.project,
            ),
            (self.child.translation.language, self.parent.translation.language, None),
        ):
            with (
                self.subTest(language=language, source=source, project=project),
                self.assertRaises(ValidationError),
            ):
                WorkflowSetting(
                    language=language, source_language=source, project=project
                ).clean()

    def test_three_language_cycle(self) -> None:
        self.configure()
        self.configure(self.parent, self.grandchild)
        with self.assertRaises(ValidationError):
            self.configure(self.grandchild, self.child)

    def test_global_form(self) -> None:
        self.assertNotIn("source_language", WorkflowSettingForm().fields)
        form = WorkflowSettingForm(
            project=self.project, language=self.child.translation.language
        )
        choices = cast(
            "forms.ModelChoiceField", form.fields["source_language"]
        ).queryset
        assert choices is not None
        self.assertIn(self.parent.translation.language, choices)
        self.assertNotIn(self.child.translation.language, choices)

    def test_form_validates_new_instance(self) -> None:
        form = WorkflowSettingForm(
            {
                "workflow-enable": "1",
                "workflow-source_language": self.parent.translation.language_id,
                "workflow-suggestion_autoaccept": "0",
            },
            project=self.project,
            language=self.child.translation.language,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.child.refresh_from_db()
        self.assertEqual(self.child.translation_parent_id, self.parent.pk)

    def test_plural_parent(self) -> None:
        parent = self.parent.translation.unit_set.get(source__startswith="Orangutan")
        child = self.child.translation.unit_set.get(id_hash=parent.id_hash)
        self.set_target(parent, "Affe\x1e\x1eAffen")
        self.configure(child, parent)
        child.refresh_from_db()
        self.assertEqual(child.get_effective_source_plurals(), ["Affe", "Affen"])
        self.assertEqual(child.effective_source_plural, parent.translation.plural)
        self.assertEqual(child.get_source_plurals(), parent.get_source_plurals())

    def test_missing_plurals_with_single_form_parent(self) -> None:
        japanese = Language.objects.get(code="ja")
        Translation.objects.filter(pk=self.parent.translation_id).update(
            language=japanese, plural=japanese.plural
        )
        parent = Unit.objects.get(
            translation_id=self.parent.translation_id, source__startswith="Orangutan"
        )
        child = self.child.translation.unit_set.get(id_hash=parent.id_hash)
        self.set_target(parent, "オランウータン")
        self.configure(child, parent)
        self.set_target(child, "Orangutan")
        child = Unit.objects.get(pk=child.pk)
        self.assertEqual(child.get_effective_source_plurals(), ["オランウータン"])
        self.assertEqual(child.get_target_plurals(), ["Orangutan", "", ""])
        self.assertTrue(child.check_set.filter(name="plurals").exists())

        self.set_target(child, join_plural(["Orangutan", "Orangutani", "Orangutanů"]))
        self.assertFalse(child.check_set.filter(name="plurals").exists())

    def test_parent_change_invalidates_ai_diagnostics(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        self.child.refresh_from_db()
        self.child.check_set.create(
            name="ai_accuracy",
            metadata={
                "fingerprint": evaluation_fingerprint(self.child),
                "issues": [{"severity": "minor", "explanation": "Old source issue"}],
            },
        )
        self.child.invalidate_checks_cache()
        self.child.run_checks()
        self.assertTrue(self.child.check_set.filter(name="ai_accuracy").exists())
        self.set_target(self.parent, "Guten Tag")
        self.assertFalse(self.child.check_set.filter(name="ai_accuracy").exists())

    def test_parent_language_invalidates_ai_fingerprint(self) -> None:
        self.set_target(self.parent, "Identical source")
        self.set_target(self.grandchild, "Identical source")
        workflow = self.configure()
        self.set_target(self.child, "Ahoj")
        self.child.refresh_from_db()
        fingerprint = evaluation_fingerprint(self.child)
        workflow.source_language = self.grandchild.translation.language
        workflow.save()
        self.child.refresh_from_db()
        self.assertEqual(self.child.effective_source, "Identical source")
        self.assertNotEqual(evaluation_fingerprint(self.child), fingerprint)

    def test_space_fixups_use_parent(self) -> None:
        self.configure()
        for check in (BeginSpaceCheck(), EndSpaceCheck()):
            for source, target in (("  Hallo  ", "Ahoj"), ("Hallo", "  Ahoj  ")):
                with self.subTest(check=check.check_id, source=source):
                    self.set_target(self.parent, source)
                    self.set_target(self.child, target)
                    self.child.refresh_from_db()
                    self.assertTrue(check.check_single(source, target, self.child))
                    fixups = check.get_fixup(self.child)
                    assert fixups is not None
                    for item in fixups:
                        assert item[0] == "regex"
                        _kind, pattern, replacement, _flags = item
                        target = re.sub(pattern, replacement, target)
                    self.assertFalse(check.check_single(source, target, self.child))

    @override_settings(LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH=True)
    def test_length_limit_uses_parent(self) -> None:
        self.set_target(self.parent, "Langer deutscher Ausgangstext " * 10)
        self.configure()
        self.child.refresh_from_db()
        self.assertEqual(self.child.get_max_length(), len(self.parent.target) * 10)
        self.child.extra_flags = "max-length:50"
        self.child.save(update_fields=["extra_flags"])
        child = Unit.objects.get(pk=self.child.pk)
        self.assertEqual(child.get_max_length(), 50)

    def test_search_uses_effective_source(self) -> None:
        self.set_target(self.parent, "Elterntext")
        self.configure()
        units = self.child.translation.unit_set
        for query in (
            "Elterntext",
            "source:Elterntext",
            "source:=Elterntext",
            'source:r"^Eltern"',
        ):
            with self.subTest(query=query):
                self.assertIn(self.child, units.search(query, parser="unit"))
        self.assertNotIn(self.child, units.search("source:Hello", parser="unit"))
        self.assertNotIn(
            self.child, units.search("NOT source:Elterntext", parser="unit")
        )
        self.assertIn(
            self.grandchild,
            self.grandchild.translation.unit_set.search("source:Hello", parser="unit"),
        )

    def test_suggestion_checks_use_parent(self) -> None:
        self.child.extra_flags = "python-format"
        self.child.save(update_fields=["extra_flags"])
        self.set_target(self.parent, "Hallo %(parent)s")
        self.configure()
        self.child.refresh_from_db()
        suggestion = Suggestion(unit=self.child, target="Ahoj", user=self.user)
        self.assertIn(
            "python_format", [check.name for check in suggestion.get_checks()]
        )
        suggestion.target = "Ahoj %(parent)s"
        self.assertNotIn(
            "python_format", [check.name for check in suggestion.get_checks()]
        )

    def test_blocked_memory_stays_pending(self) -> None:
        self.project.translation_review = False
        self.project.save(update_fields=["translation_review"])
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        for text in ("Hallo", "Geänderter Text"):
            with self.subTest(text=text):
                self.set_target(self.parent, text, STATE_NEEDS_REWRITING)
                self.child.refresh_from_db()
                self.assertEqual(self.child.state, STATE_READONLY)
                payload = get_unit_memory_update(self.child)
                assert payload is not None
                self.assertEqual(
                    get_memory_status(self.project, payload["unit_state"]),
                    Memory.STATUS_PENDING,
                )
                self.set_target(self.parent, text)
        self.set_target(self.child, "Aktualizováno")
        payload = get_unit_memory_update(self.child)
        assert payload is not None
        self.assertEqual(
            get_memory_status(self.project, payload["unit_state"]), Memory.STATUS_ACTIVE
        )

    def test_historical_source_uses_canonical_metadata(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.child.refresh_from_db()
        with patch(
            "weblate.trans.formatting.format_translation", return_value=""
        ) as render:
            format_unit_source(self.child, value=self.child.source)
        self.assertEqual(
            render.call_args.kwargs["language"], self.component.source_language
        )
        self.assertEqual(
            render.call_args.kwargs["plural"], self.child.source_unit.translation.plural
        )

    def test_source_history_preserves_empty_parent(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        self.set_target(self.parent, "", STATE_EMPTY)
        change = self.child.change_set.filter(action=ActionEvents.SOURCE_CHANGE).latest(
            "pk"
        )
        with patch(
            "weblate.trans.change_display.format_unit_source", wraps=format_unit_source
        ) as render:
            fields = ShowChangeSource(change).get_change_details_fields()
        self.assertEqual(render.call_args.kwargs["value"], "")
        self.assertNotIn(self.child.source.strip(), fields[0]["content"])
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)

    def test_parent_history_retains_source_language(self) -> None:
        self.set_target(self.parent, "Hallo")
        workflow = self.configure()
        self.set_target(self.parent, "Guten Tag")
        change = self.child.change_set.filter(action=ActionEvents.SOURCE_CHANGE).latest(
            "pk"
        )
        workflow.delete()
        change.refresh_from_db()
        with patch(
            "weblate.trans.change_display.format_unit_source", wraps=format_unit_source
        ) as render:
            ShowChangeSource(change).get_change_details_fields()
        self.assertEqual(
            render.call_args.kwargs["language"], self.parent.translation.language
        )
        self.assertEqual(
            render.call_args.kwargs["plural"], self.parent.translation.plural
        )

    def test_snapshots_preserve_rtl_source_rendering(self) -> None:
        arabic = Language.objects.get(code="ar")
        Translation.objects.filter(pk=self.parent.translation_id).update(
            language=arabic, plural=arabic.plural
        )
        self.parent = Unit.objects.get(pk=self.parent.pk)
        self.set_target(self.parent, "مصدر 123!")
        workflow = self.configure()
        self.set_target(self.child, "Child translation")
        target_change = self.child.generate_change(
            self.user, self.user, ActionEvents.CHANGE, check_new=False
        )
        self.set_target(self.grandchild, "Italian source")
        workflow.source_language = self.grandchild.translation.language
        workflow.save()
        self.child.refresh_from_db()

        sources = get_source_changes(self.child)
        self.assertEqual(len(sources), 2)
        previous, current = sources[0], sources[1]
        self.assertEqual(previous["language"].direction, "rtl")
        self.assertEqual(current["language"].direction, "ltr")
        source_change = self.child.change_set.filter(
            action=ActionEvents.SOURCE_CHANGE
        ).latest("pk")
        fields = ShowChangeSource(source_change).get_change_details_fields()
        self.assertIn('dir="rtl"', fields[0]["content"])
        self.assertIn('dir="ltr"', fields[1]["content"])
        target_change.refresh_from_db()
        fields = ShowChangeContent(target_change).get_change_details_fields()
        self.assertIn('dir="rtl"', fields[0]["content"])

    def test_format_description_uses_parent(self) -> None:
        self.child.extra_flags = "python-format"
        self.child.save(update_fields=["extra_flags"])
        self.set_target(self.parent, "Hallo %(parent)s")
        self.configure()
        self.set_target(self.child, "Ahoj %(target)s")
        check = self.child.check_set.get(name="python_format")
        description = str(check.get_description())
        self.assertIn("%(parent)s", description)
        self.assertIn("%(target)s", description)

    def test_duplicate_description_uses_parent(self) -> None:
        self.set_target(self.parent, "parent parent")
        self.configure()
        self.set_target(self.child, "parent parent target target")
        check = self.child.check_set.get(name="duplicate")
        description = str(check.get_description())
        self.assertIn("<code>target</code>", description)
        self.assertNotIn("<code>parent</code>", description)

    def test_llm_project_example_uses_parent(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        self.child.refresh_from_db()
        self.assertEqual(
            BaseLLMTranslation._get_project_example_source_plurals(  # ruff: ignore[private-member-access]
                self.child, "de"
            ),
            ["Hallo"],
        )
        self.assertEqual(
            BaseLLMTranslation._get_project_example_source_plurals(  # ruff: ignore[private-member-access]
                self.child, "en"
            ),
            self.child.get_source_plurals(),
        )

    def test_deepl_glossary_uses_parent_language(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.child.refresh_from_db()
        machine = DeepLTranslation({"key": "test", "url": "https://api.deepl.com/"})
        glossary_name = machine.glossary_name_format.format(
            project=self.project.pk,
            source_language="DE",
            target_language="CS",
            checksum=machine.tsv_checksum("Hallo\tAhoj"),
        )
        with (
            patch.object(machine, "is_glossary_supported", return_value=True),
            patch.object(
                machine,
                "get_glossaries",
                side_effect=[{}, {glossary_name: "new-glossary"}],
            ),
            patch.object(machine, "create_glossary") as create,
            patch(
                "weblate.glossary.models.get_glossary_tsv", return_value="Hallo\tAhoj"
            ) as tsv,
        ):
            machine.get_glossary_id("DE", "CS", self.child)
        tsv.assert_called_once_with(
            self.child.translation, source_language=self.parent.translation.language
        )
        self.assertEqual(create.call_args.args[:2], ("DE", "CS"))
        self.assertEqual(create.call_args.args[3], "Hallo\tAhoj")

    def test_machinery_source_selection_survives_provider_code_mapping(self) -> None:
        self.set_target(self.parent, "Parent source")
        self.configure()
        unit = Unit.objects.get(pk=self.child.pk)
        secondary = self.grandchild.translation.language
        unit.translation.component.secondary_language = secondary
        machine = DeepLTranslation({"key": "test", "url": "https://api.deepl.com/"})
        for selection, language, kwargs in (
            (
                SourceLanguageChoices.AUTO,
                unit.effective_source_language,
                {"source_language": unit.effective_source_language},
            ),
            (
                SourceLanguageChoices.SOURCE,
                unit.translation.component.source_language,
                {},
            ),
            (SourceLanguageChoices.SECONDARY, secondary, {}),
        ):
            with (
                self.subTest(selection=selection),
                patch.object(machine, "map_language_code", return_value="DE"),
                patch(
                    "weblate.glossary.models.get_glossary_tsv", return_value="a\tb"
                ) as tsv,
            ):
                machine.settings["source_language"] = selection
                self.assertEqual(machine.get_unit_source_language(unit), language)
                machine.get_glossary_tsv("DE", unit)
                tsv.assert_called_once_with(unit.translation, **kwargs)
                tsv.reset_mock()
                machine.get_glossary_cache_part(unit)
                tsv.assert_called_once_with(unit.translation, **kwargs)

    def test_parent_glossary_cache_is_invalidated(self) -> None:
        self.configure()
        key = self.project.get_glossary_tsv_cache_key(
            self.parent.translation.language, self.child.translation.language
        )
        cache.set(key, "stale glossary", 3600)
        self.project.invalidate_glossary_cache()
        self.assertIsNone(cache.get(key))

    def test_parent_changes_schedule_memory_update(self) -> None:
        self.set_target(self.parent, self.child.source)
        self.set_target(self.child, "Ahoj")
        with patch("weblate.trans.models.unit.schedule_memory_update") as schedule:
            self.configure()
            payload = next(
                call.args[0]
                for call in schedule.call_args_list
                if call.args[0]["target"] == "Ahoj"
            )
            self.assertEqual(
                payload["source_language_id"], self.parent.translation.language_id
            )
            self.assertEqual(payload["source"], self.child.source)
            self.assertEqual(payload["unit_state"], STATE_NEEDS_REWRITING)
            self.set_target(self.child, "Ahoj")
            schedule.reset_mock()
            self.set_target(self.parent, "Hallo")
            payload = next(
                call.args[0]
                for call in schedule.call_args_list
                if call.args[0]["target"] == "Ahoj"
            )
            self.assertEqual(payload["source"], "Hallo")
            self.assertEqual(payload["unit_state"], STATE_NEEDS_REWRITING)

    def test_memory_rebuild_prefetches_parent(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        updates = []

        def payload(
            unit: Unit, user: User | None, component: Component, project: Project
        ) -> MemoryUpdatePayload | None:
            if unit.translation_parent_id:
                with self.assertNumQueries(0):
                    source = unit.effective_source
                    self.assertEqual(unit.effective_source_language.code, "de")
                if unit.pk == self.child.pk:
                    self.assertEqual(source, "Hallo")
                updates.append(unit.pk)
            return get_unit_memory_update(unit, user, component, project)

        with (
            patch("weblate.memory.tasks.get_unit_memory_update", side_effect=payload),
            patch("weblate.memory.tasks.schedule_memory_updates"),
        ):
            import_memory(self.project.pk, self.component.pk)
        self.assertIn(self.child.pk, updates)

    def test_secondary_languages_are_not_mutated(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.child.refresh_from_db()
        language_id = self.parent.translation.language_id
        self.user.profile.__dict__["secondary_language_ids"] = {language_id}
        self.assertEqual(self.child.get_secondary_units(self.user), [])
        self.assertEqual(self.user.profile.secondary_language_ids, {language_id})
        self.assertIn(self.parent, self.grandchild.get_secondary_units(self.user))

    def test_source_badges_preload_languages(self) -> None:
        self.configure()
        self.configure(self.grandchild, self.parent)
        self.project.project_languages.preload_workflow_settings()
        with self.assertNumQueries(0):
            for language in (
                self.child.translation.language,
                self.grandchild.translation.language,
            ):
                workflow = self.project.project_languages[language].workflow_settings
                self.assertEqual(workflow.source_language.code, "de")

    def test_memory_uses_parent_language(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        self.child.refresh_from_db()
        update = get_unit_memory_update(self.child, self.user)
        assert update is not None
        self.assertEqual(update["source"], "Hallo")
        self.assertEqual(
            update["source_language_id"], self.parent.translation.language_id
        )

    def test_independent_readonly(self) -> None:
        self.child.extra_flags = "read-only"
        self.child.state = STATE_READONLY
        self.child.save()
        self.configure()
        self.set_target(self.parent, "Hallo")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)

    def test_format_readonly_survives_parent_changes(self) -> None:
        self.set_target(self.child, "Protected", STATE_READONLY)
        self.configure()
        self.set_target(self.parent, "Hallo")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_READONLY)
        self.assertEqual(self.child.original_state, STATE_READONLY)

    def test_canonical_change_prevents_parent_revert(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        self.set_target(self.child, "Ahoj")
        self.set_target(self.parent, "Guten Tag")
        self.child.refresh_from_db()
        self.child.source = "Changed canonical source"
        self.child.save()
        self.set_target(self.parent, "Hallo")
        self.child.refresh_from_db()
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)

    def test_translation_removal_and_recreation(self) -> None:
        self.set_target(self.parent, "Hallo")
        self.configure()
        language = self.parent.translation.language
        Translation.objects.filter(pk=self.parent.translation_id).delete()
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.effective_source_language.code, "en")
        self.assertTrue(Unit.objects.filter(pk=self.grandchild.pk).exists())
        self.assertEqual(
            WorkflowSetting.objects.get(
                language=self.child.translation.language
            ).source_language_id,
            language.pk,
        )
        setting = WorkflowSetting.objects.get(
            project=self.project, language=self.child.translation.language
        )
        setting.full_clean()
        form = WorkflowSettingForm(instance=setting, project=self.project)
        choices = cast(
            "forms.ModelChoiceField", form.fields["source_language"]
        ).queryset
        assert choices is not None
        self.assertIn(language, choices)

    def test_component_move_reconciles_parent(self) -> None:
        self.configure()
        destination = Project.objects.create(
            name="Destination", slug="destination", web="https://example.com/"
        )
        self.component.project = destination
        self.component.save(update_fields=["project"])
        self.child.refresh_from_db()
        self.assertIsNone(self.child.translation_parent_id)
        self.assertEqual(self.child.state, STATE_EMPTY)

    def test_api_prefetched_sources_do_not_query_per_unit(self) -> None:
        self.configure()
        units = list(self.child.translation.unit_set.prefetch_api())
        with self.assertNumQueries(0):
            for unit in units:
                self.assertEqual(unit.effective_source_language.code, "de")
                unit.get_effective_source_plurals()
                self.assertEqual(unit.effective_source_plural.number, 2)

    def test_cleanup_preserves_workflow_source_language(self) -> None:
        language = Language.objects.auto_get_or_create("de_CUSTOM")
        unused = Language.objects.auto_get_or_create("de_UNUSED")
        self.assertTrue(language.show_language_code)
        self.assertTrue(unused.show_language_code)
        Translation.objects.filter(pk=self.parent.translation_id).update(
            language=language
        )
        parent = Unit.objects.get(pk=self.parent.pk)
        workflow = self.configure(parent=parent)
        parent.translation.delete()
        self.assertFalse(language.translation_set.exists())
        call_command("cleanup_languages", delete=True, stdout=StringIO())
        workflow.refresh_from_db()
        self.assertEqual(workflow.source_language_id, language.pk)
        self.assertTrue(Language.objects.filter(pk=language.pk).exists())
        self.assertFalse(Language.objects.filter(pk=unused.pk).exists())

    def test_llm_uses_translation_source_plural(self) -> None:
        plural = Plural.objects.create(
            language=self.parent.translation.language, number=2, formula="n > 1"
        )
        Translation.objects.filter(pk=self.parent.translation_id).update(plural=plural)
        self.configure()
        child = Unit.objects.get(pk=self.child.pk)
        self.assertNotEqual(plural, child.effective_source_language.plural)
        for language_code in (None, "de"):
            with self.subTest(language_code=language_code):
                self.assertEqual(
                    BaseLLMTranslation._get_source_plural(  # ruff: ignore[private-member-access]
                        child, language_code
                    ),
                    plural,
                )

    def test_prefetched_sources_do_not_query_per_unit(self) -> None:
        self.configure()
        units = list(
            self.component.translation_set.get(language_code="cs")
            .unit_set.prefetch()
            .prefetch_source()
        )
        with self.assertNumQueries(0):
            for unit in units:
                self.assertEqual(unit.effective_source_language.code, "de")
                unit.get_effective_source_plurals()
                self.assertEqual(unit.effective_source_plural.number, 2)

    def test_reconciliation_batches_workflows(self) -> None:
        self.configure()
        with CaptureQueriesContext(connection) as queries:
            reconcile_component_parents(self.component)
        workflow_queries = [
            query for query in queries if '"trans_workflowsetting"' in query["sql"]
        ]
        self.assertEqual(len(workflow_queries), 1)

    def test_machine_translation_uses_parent(self) -> None:
        from weblate.machinery.base import MachineTranslation  # ruff: ignore[import-outside-top-level]

        self.set_target(self.parent, "Hallo")
        self.configure()
        self.child.refresh_from_db()
        machine = MachineTranslation({})
        with (
            patch.object(
                machine, "get_languages", return_value=("de", "cs")
            ) as languages,
            patch.object(
                machine, "download_multiple_translations", return_value={"Hallo": []}
            ) as download,
        ):
            machine.translate(self.child, self.user)
        languages.assert_called_once_with(
            self.parent.translation.language, self.child.translation.language
        )
        self.assertEqual(
            download.call_args.args[:3], ("de", "cs", [("Hallo", self.child)])
        )


class SourceLanguageFileTest(ViewTestCase):
    def test_machinery_batch_keeps_components_separate(self) -> None:
        create = (
            self.create_po_mono
            if self.component.file_format == "po-mono"
            else self.create_po_new_base
        )
        other = create(name="Other component", project=self.project)
        children = []
        expected = []
        for component, text in (
            (self.component, "First parent"),
            (other, "Second parent"),
        ):
            child = component.translation_set.get(language_code="cs").unit_set.order_by(
                "pk"
            )[0]
            parent = component.translation_set.get(language_code="de").unit_set.get(
                id_hash=child.id_hash
            )
            parent.translate(self.user, text, STATE_TRANSLATED, propagate=False)
            children.append(child)
            expected.append(parent.target)
        WorkflowSetting.objects.create(
            project=self.project,
            language=children[0].translation.language,
            source_language=Language.objects.get(code="de"),
        )
        children = [Unit.objects.get(pk=child.pk) for child in children]
        machine = WeblateTranslation({})
        with patch.object(
            machine,
            "_translate_sources",
            side_effect=lambda _source, _target, sources, *_args: [
                [{"text": text, "quality": 100}] for text, _unit in sources
            ],
        ):
            machine.batch_translate(children)
        self.assertEqual(
            [child.machinery["translation"][0] for child in children], expected
        )

    def test_terminology_sync_resolves_parents_after_batch(self) -> None:
        self.component.manage_units = True
        self.component.save(update_fields=["manage_units"])
        source_translation = self.component.source_translation
        source = source_translation.unit_set.order_by("pk")[0]
        targets = list(self.component.translation_set.exclude(pk=source_translation.pk))
        child_translation, parent_translation = targets[0], targets[1]
        WorkflowSetting.objects.create(
            project=self.project,
            language=child_translation.language,
            source_language=parent_translation.language,
        )
        source.extra_flags = "terminology"
        source.save(sync_terminology=False)
        source.unit_set.exclude(pk=source.pk).delete()
        self.component.unload_sources()
        source_translation.sync_terminology()
        child = child_translation.unit_set.get(id_hash=source.id_hash)
        parent = parent_translation.unit_set.get(id_hash=source.id_hash)
        self.assertEqual(child.translation_parent_id, parent.pk)
        self.assertEqual(child.state, STATE_READONLY)
        self.assertTrue(child.translation_parent_blocked)

    def test_plural_form_edit_reconciles_children(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        parent.translate(self.user, "Parent", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child", STATE_TRANSLATED)
        plural = parent.translation.plural
        previous_formula = plural.formula
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-plural", kwargs={"pk": plural.pk}),
            {"number": "2", "formula": "n > 1"},
        )
        self.assertEqual(response.status_code, 302)
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(
            child.details["translation_parent"]["previous"]["formula"], previous_formula
        )
        self.assertEqual(
            child.details["translation_parent"]["applied"]["formula"], "n > 1"
        )
        self.assertTrue(
            child.change_set.filter(
                action=ActionEvents.SOURCE_CHANGE,
                details__source_snapshot__formula="n > 1",
            ).exists()
        )

    def test_listing_batches_source_languages(self) -> None:
        parent = self.component.translation_set.get(language_code="de")
        for code in ("cs", "it"):
            WorkflowSetting.objects.create(
                project=self.project,
                language=Language.objects.get(code=code),
                source_language=parent.language,
            )
        with patch.object(
            Translation.effective_source_translation,
            "func",
            side_effect=AssertionError("Source language was not loaded in bulk"),
        ):
            response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Source: German")
        translations = response.context["translations"]
        with self.assertNumQueries(0):
            for translation in translations:
                if translation.language.code in {"cs", "it"}:
                    self.assertEqual(
                        translation.effective_source_language, parent.language
                    )

    def test_target_history_preserves_effective_source(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        parent.translate(self.user, "Historical parent", STATE_TRANSLATED)
        historical_source = parent.target
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        change = child.change_set.filter(
            action__in=[ActionEvents.NEW, ActionEvents.CHANGE]
        ).latest("pk")
        parent.translate(self.user, "Updated parent", STATE_TRANSLATED)
        change.refresh_from_db()
        self.assertEqual(change.get_source(), historical_source)
        with patch(
            "weblate.trans.change_display.format_unit_source", wraps=format_unit_source
        ) as render:
            ShowChangeContent(change).get_change_details_fields()
        self.assertEqual(render.call_args.kwargs["value"], historical_source)
        self.assertEqual(
            render.call_args.kwargs["language"], parent.translation.language
        )
        self.assertEqual(render.call_args.kwargs["plural"], parent.translation.plural)

    def test_parent_plural_import_invalidates_child(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent_translation = self.component.translation_set.get(language_code="de")
        parent = parent_translation.unit_set.get(id_hash=child.id_hash)
        parent.translate(self.user, "Parent translation", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent_translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        old_plural = parent_translation.plural
        plural = Plural.objects.create(
            language=parent_translation.language,
            source=Plural.SOURCE_GETTEXT,
            number=2,
            formula="n > 1",
        )
        parent_translation.drop_store_cache()
        with (
            source_operation(self.component),
            patch.object(
                type(parent_translation.store), "get_plural", return_value=plural
            ),
        ):
            parent_translation.check_sync(force=True)
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(
            child.details["translation_parent"]["previous"]["plural_id"], old_plural.pk
        )
        self.assertNotIn("previous_translation_parent_plural", child.details)
        change = child.change_set.filter(action=ActionEvents.SOURCE_CHANGE).latest("pk")
        self.assertEqual(
            change.details["previous_source_snapshot"]["plural_id"], old_plural.pk
        )
        self.assertEqual(change.details["source_snapshot"]["plural_id"], plural.pk)

    def test_listing_shows_fallback_source_language(self) -> None:
        self.create_po_new_base(name="Other component", project=self.project)
        parent_language = self.component.translation_set.get(
            language_code="de"
        ).language
        self.component.translation_set.filter(language=parent_language).delete()
        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            source_language=parent_language,
        )
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Source: English")
        self.assertNotContains(response, "Source: German")

    def test_editor_shows_all_previous_plural_forms(self) -> None:
        previous = self.translation.unit_set.order_by("pk")[0]
        child = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=previous.id_hash
        )
        current = self.component.translation_set.get(language_code="it").unit_set.get(
            id_hash=previous.id_hash
        )
        previous.translate(
            self.user,
            join_plural(["Czech one", "Czech few", "Czech many"]),
            STATE_TRANSLATED,
        )
        current.translate(
            self.user, join_plural(["Italian one", "Italian many"]), STATE_TRANSLATED
        )
        workflow = WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=previous.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "German translation", STATE_TRANSLATED)
        workflow.source_language = current.translation.language
        workflow.save()
        response = self.client.get(child.get_absolute_url())
        for text in (
            "Previous source",
            "Czech one",
            "Czech few",
            "Czech many",
            "Italian one",
            "Italian many",
        ):
            self.assertContains(response, text)
        response = self.client.get(
            reverse("zen", kwargs={"path": child.translation.get_url_path()}),
            {"q": f"id:{child.pk}"},
        )
        self.assertContains(response, "Czech many")
        self.assertContains(response, "Previous source")

    def test_blocked_child_persists_underlying_state(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        parent.translate(self.user, "Original parent", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        parent.translate(self.user, "Changed parent", STATE_NEEDS_REWRITING)
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_READONLY)
        self.assertEqual(child.original_state, STATE_NEEDS_REWRITING)
        pending = PendingUnitChange.objects.filter(unit=child).latest("pk")
        self.assertEqual(pending.state, STATE_NEEDS_REWRITING)
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.save(update_fields=["commit_policy"])
        translation = Translation.objects.get(pk=child.translation_id)
        self.assertFalse(
            PendingUnitChange.objects.for_translation(translation).exists()
        )
        self.project.commit_policy = CommitPolicyChoices.ALL
        self.project.save(update_fields=["commit_policy"])
        self.component.commit_pending("test", self.user)
        self.translation.drop_store_cache()
        stored, _ = self.translation.store.find_unit(child.context, child.source)
        self.assertTrue(stored.is_fuzzy())
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_READONLY)

    def test_propagated_parent_invalidates_child(self) -> None:
        create_component = (
            self.create_po_mono
            if self.component.file_format == "po-mono"
            else self.create_po_new_base
        )
        other = create_component(name="Other component", project=self.project)
        child = other.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        parent = other.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        source_parent = self.component.translation_set.get(
            language_code="de"
        ).unit_set.get(source=child.source)
        parent.translate(
            self.user, "Previous parent", STATE_TRANSLATED, propagate=False
        )
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(
            self.user, "Child translation", STATE_TRANSLATED, propagate=False
        )
        previous = parent.target
        source_parent.translate(self.user, "Updated parent", STATE_TRANSLATED)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(child.effective_source, parent.target)
        self.assertIn("Updated parent", parent.target)
        self.assertEqual(child.state, STATE_NEEDS_REWRITING)
        self.assertEqual(child.effective_previous_source, previous)

    def test_import_restores_missing_parent(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent_translation = self.component.translation_set.get(language_code="de")
        parent = parent_translation.unit_set.get(id_hash=child.id_hash)
        parent.delete()
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent_translation.language,
        )
        child.refresh_from_db()
        self.assertIsNone(child.translation_parent_id)
        parent_translation.check_sync(force=True)
        child.refresh_from_db()
        self.assertIsNotNone(child.translation_parent_id)
        assert child.translation_parent is not None
        self.assertEqual(child.translation_parent.translation_id, parent_translation.pk)

    def test_parent_import_invalidates_child(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent_translation = self.component.translation_set.get(language_code="de")
        parent = parent_translation.unit_set.get(id_hash=child.id_hash)
        parent.translate(self.user, "Parent translation", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent_translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        parent_translation.drop_store_cache()
        disk_unit, _ = parent_translation.store.find_unit(parent.context, parent.source)
        disk_unit.set_target("Updated parent")
        parent_translation.store.save()
        parent_translation.drop_store_cache()
        parent_translation.check_sync(force=True)
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_NEEDS_REWRITING)
        self.assertIn("Updated parent", child.effective_source)
        self.assertIn("Child translation", child.target)

    def test_editor_uses_parent_source(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        parent.translate(self.user, "Parent translation", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        self.client.force_login(self.user)
        response = self.client.get(child.get_absolute_url())
        self.assertContains(response, "Parent translation")
        self.assertContains(response, parent.get_absolute_url())
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Source: German")

    def test_zen_uses_effective_source(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        parent.translate(self.user, "Old parent", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        parent.translate(self.user, "New parent", STATE_TRANSLATED)
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("zen", kwargs=self.kw_translation), {"q": f"id:{child.pk}"}
        )
        self.assertContains(response, parent.get_absolute_url())
        self.assertContains(response, "German")
        self.assertContains(response, "Source change")
        self.assertContains(response, "New")
        self.assertContains(response, "Old")

    def test_report_targets_parent(self) -> None:
        self.project.source_review = True
        self.project.save(update_fields=["source_review"])
        child = self.translation.unit_set.order_by("pk")[0]
        parent = self.component.translation_set.get(language_code="de").unit_set.get(
            id_hash=child.id_hash
        )
        parent.translate(self.user, "Parent source", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        canonical = child.source_unit
        canonical_state = canonical.state
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("comment", kwargs={"pk": child.pk}),
            {"scope": "report", "comment": "Problem in parent"},
        )
        self.assertEqual(response.status_code, 302)
        parent.refresh_from_db()
        canonical.refresh_from_db()
        self.assertEqual(parent.state, STATE_NEEDS_REWRITING)
        self.assertTrue(parent.comment_set.filter(comment="Problem in parent").exists())
        self.assertFalse(
            canonical.comment_set.filter(comment="Problem in parent").exists()
        )
        self.assertEqual(canonical.state, canonical_state)
        child.refresh_from_db()
        self.assertEqual(
            child.all_comments.filter(comment="Problem in parent").count(), 1
        )
        self.assertContains(
            self.client.get(child.get_absolute_url()), "Problem in parent"
        )

    def test_settings_source_language(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.client.force_login(self.user)
        language = self.translation.language
        parent = self.component.translation_set.get(language_code="de")
        url = reverse(
            "settings",
            kwargs={"path": self.project.project_languages[language].get_url_path()},
        )
        response = self.client.post(
            url,
            {
                "workflow-enable": "1",
                "workflow-source_language": parent.language_id,
                "workflow-suggestion_autoaccept": "0",
            },
            follow=True,
        )
        self.assertContains(response, "Settings saved")
        self.assertEqual(
            WorkflowSetting.objects.get(
                project=self.project, language=language
            ).source_language_id,
            parent.language_id,
        )

    def test_round_trip(self) -> None:
        child = self.translation.unit_set.order_by("pk")[0]
        parent_translation = self.component.translation_set.get(language_code="de")
        parent = parent_translation.unit_set.get(id_hash=child.id_hash)
        parent.translate(self.user, "Parent translation", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        canonical_source, identity = child.source, child.id_hash
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        for translation in self.component.translation_set.exclude(filename=""):
            translation.check_sync(force=True)
        child.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(child.source, canonical_source)
        self.assertEqual(child.id_hash, identity)
        self.assertEqual(child.translation_parent_id, parent.pk)
        self.assertIn("Child translation", child.target)
        self.assertIn("Parent translation", parent.target)
        self.assertEqual(child.state, STATE_TRANSLATED)
        self.assertEqual(child.source_unit_id, parent.source_unit_id)


class SourceLanguageMonoFileTest(SourceLanguageFileTest):
    def test_canonical_edit_preserves_dependency_blocking(self) -> None:
        source = self.component.source_translation.unit_set.order_by("pk")[0]
        # Unit PK order processes this parent before its child in the batch.
        targets = list(source.unit_set.exclude(pk=source.pk).order_by("pk"))
        parent, child = targets[0], targets[1]
        parent.translate(self.user, "Parent source", STATE_TRANSLATED, propagate=False)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child.translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child target", STATE_TRANSLATED, propagate=False)
        source.translate(self.user, "Changed canonical source", STATE_TRANSLATED)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.state, STATE_NEEDS_REWRITING)
        self.assertEqual(child.state, STATE_READONLY)
        self.assertTrue(child.translation_parent_blocked)
        self.assertTrue(child.details["translation_parent"]["blocked"])
        self.assertFalse(self.user.has_perm("unit.edit", child))

    def create_component(self) -> Component:
        return self.create_po_mono()


class SourceLanguageIntermediateTest(ViewTestCase):
    def create_component(self) -> Component:
        return self.create_json_intermediate()

    def test_intermediate_source_blocks_custom_children(self) -> None:
        source = self.component.source_translation.unit_set.get(source="Hello world!\n")
        parent = source.unit_set.get(translation=self.translation)
        child_translation = self.component.add_new_language(
            Language.objects.get(code="it"), None, show_messages=False
        )
        assert child_translation is not None
        child = child_translation.unit_set.get(id_hash=parent.id_hash)
        parent.translate(self.user, "Parent", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child_translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child", STATE_TRANSLATED)
        source.translate(self.user, source.target, STATE_NEEDS_REWRITING)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.state, STATE_READONLY)
        self.assertEqual(parent.original_state, STATE_TRANSLATED)
        self.assertTrue(child.translation_parent_blocked)
        self.assertEqual(child.state, STATE_READONLY)
        self.assertFalse(self.user.has_perm("unit.edit", child))
        source.translate(self.user, source.target, STATE_TRANSLATED)
        child.refresh_from_db()
        self.assertFalse(child.translation_parent_blocked)
        self.assertEqual(child.state, STATE_TRANSLATED)

    def test_intermediate_parent_state(self) -> None:
        source = self.component.source_translation.unit_set.get(source="Hello world!\n")
        parent = source.unit_set.get(translation=self.translation)
        child_translation = self.component.add_new_language(
            Language.objects.get(code="it"), None, show_messages=False
        )
        assert child_translation is not None
        child = child_translation.unit_set.get(id_hash=parent.id_hash)
        parent.translate(self.user, "Parent translation", STATE_TRANSLATED)
        WorkflowSetting.objects.create(
            project=self.project,
            language=child_translation.language,
            source_language=parent.translation.language,
        )
        child.refresh_from_db()
        child.translate(self.user, "Child translation", STATE_TRANSLATED)
        parent.translate(self.user, parent.target, STATE_NEEDS_REWRITING)
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_READONLY)
        parent.translate(self.user, parent.target, STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        self.component.do_file_scan()
        child.refresh_from_db()
        self.assertEqual(child.state, STATE_TRANSLATED)
        self.assertEqual(child.translation_parent_id, parent.pk)
        self.assertEqual(child.source_unit_id, parent.source_unit_id)


class SourceLanguageConcurrencyTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        self.clone_test_repos()
        super().setUp()

    def test_concurrent_cycle_is_rejected(self) -> None:
        component = self.create_component()
        czech = component.translation_set.get(language_code="cs").language_id
        german = component.translation_set.get(language_code="de").language_id
        ready = Barrier(2)

        def configure(language_id: int, source_id: int) -> bool:
            close_old_connections()
            try:
                ready.wait(timeout=10)
                try:
                    WorkflowSetting.objects.create(
                        project_id=component.project_id,
                        language_id=language_id,
                        source_language_id=source_id,
                    )
                except ValidationError:
                    return False
                return True
            finally:
                connection.close()

        with (
            patch("weblate.trans.models.source.reconcile_project_parents"),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(configure, czech, german)
            second = executor.submit(configure, german, czech)
            self.assertCountEqual(
                [first.result(timeout=15), second.result(timeout=15)], [True, False]
            )
        self.assertEqual(
            WorkflowSetting.objects.filter(project=component.project).count(), 1
        )
