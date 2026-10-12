# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Transaction boundaries for custom translation sources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event
from time import monotonic, sleep
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Unit, WorkflowSetting
from weblate.trans.models.source import (
    source_operation,
    source_project_gate,
    source_workflows,
)
from weblate.trans.tests.utils import RepoTestMixin, clear_users_cache
from weblate.utils.state import STATE_NEEDS_REWRITING, STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Callable


def connected(operation: Callable[[], None]) -> None:
    close_old_connections()
    try:
        return operation()
    finally:
        connection.close()


class SourceOperationConcurrencyTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        Language.objects.flush_object_cache()
        self.addCleanup(Language.objects.flush_object_cache)
        clear_users_cache()
        self.addCleanup(clear_users_cache)
        self.clone_test_repos()
        super().setUp()
        self.component = self.create_component()
        self.child = self.component.translation_set.get(
            language_code="cs"
        ).unit_set.order_by("pk")[0]
        self.parent = self.component.translation_set.get(
            language_code="de"
        ).unit_set.get(id_hash=self.child.id_hash)
        self.parent.target = "Old parent"
        self.parent.state = STATE_TRANSLATED
        self.parent.save()

    def wait_for_blocked(self, pid: int) -> None:
        deadline = monotonic() + 10
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
                if cursor.fetchone()[0]:
                    return
            sleep(0.01)
        self.fail("The competing operation did not wait for the project gate")

    def assert_source_consistent(self, *, configured: bool) -> None:
        child = Unit.objects.get(pk=self.child.pk)
        parent = Unit.objects.get(pk=self.parent.pk)
        self.assertEqual(child.translation_parent_id, parent.pk if configured else None)
        self.assertEqual(
            child.effective_source, parent.target if configured else child.source
        )
        self.assertFalse(child.translation_parent_blocked)
        if configured:
            self.assertEqual(
                child.details["translation_parent"]["applied"],
                child.source_snapshot.as_dict(),
            )

    def check_switch_race(self, action: str, *, edit_first: bool) -> None:
        workflow = None
        if action != "create":
            workflow = WorkflowSetting.objects.create(
                project=self.component.project,
                language=self.child.translation.language,
                source_language=(
                    self.parent.translation.language
                    if action == "delete"
                    else self.component.source_language
                ),
            )
        # Preserve a genuinely stale, separately loaded Project instance.
        self.assertEqual(
            bool(
                self.parent.translation.component.project.translation_parent_language_ids
            ),
            action != "create",
        )
        pid_queue: Queue[int] = Queue()
        edited = Event()
        release_edit = Event()

        def identify() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid_queue.put(cursor.fetchone()[0])

        def edit() -> None:
            identify()
            with source_operation(self.parent.translation.component):
                self.parent.target = "New parent"
                self.parent.save()
                edited.set()
                if edit_first and not release_edit.wait(10):
                    msg = "Workflow did not attempt the exclusive gate"
                    raise TimeoutError(msg)

        def change_workflow() -> None:
            if action == "create":
                WorkflowSetting.objects.create(
                    project_id=self.component.project_id,
                    language_id=self.child.translation.language_id,
                    source_language_id=self.parent.translation.language_id,
                )
            elif action == "delete":
                assert workflow is not None
                WorkflowSetting.objects.filter(pk=workflow.pk).delete()
            else:
                assert workflow is not None
                current = WorkflowSetting.objects.get(pk=workflow.pk)
                current.source_language_id = self.parent.translation.language_id
                current.save()

        def configure() -> None:
            identify()
            change_workflow()

        with ThreadPoolExecutor(max_workers=2) as executor:
            if edit_first:
                edit_future = executor.submit(connected, edit)
                pid_queue.get(timeout=10)
                try:
                    self.assertTrue(edited.wait(10))
                    workflow_future = executor.submit(connected, configure)
                    self.wait_for_blocked(pid_queue.get(timeout=10))
                finally:
                    release_edit.set()
                edit_future.result(timeout=15)
                workflow_future.result(timeout=15)
            else:
                with source_project_gate([self.component.project_id], exclusive=True):
                    change_workflow()
                    edit_future = executor.submit(connected, edit)
                    self.wait_for_blocked(pid_queue.get(timeout=10))
                edit_future.result(timeout=15)
        self.assert_source_consistent(configured=action != "delete")

    def test_create_then_edit(self) -> None:
        self.check_switch_race("create", edit_first=False)

    def test_edit_then_create(self) -> None:
        self.check_switch_race("create", edit_first=True)

    def test_switch_then_edit(self) -> None:
        self.check_switch_race("switch", edit_first=False)

    def test_edit_then_switch(self) -> None:
        self.check_switch_race("switch", edit_first=True)

    def test_delete_then_edit(self) -> None:
        self.check_switch_race("delete", edit_first=False)

    def test_edit_then_delete(self) -> None:
        self.check_switch_race("delete", edit_first=True)

    def test_shared_gates_allow_concurrent_edits(self) -> None:
        ready = Barrier(2)

        def enter() -> None:
            with source_project_gate([self.component.project_id]):
                self.assertEqual(source_workflows(self.component.project_id), {})
                ready.wait(timeout=10)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(connected, enter)
            second = executor.submit(connected, enter)
            first.result(timeout=15)
            second.result(timeout=15)

    def test_bulk_delete_rejects_concurrently_moved_workflow(self) -> None:
        workflow = WorkflowSetting.objects.create(
            project=self.component.project,
            language=self.child.translation.language,
            source_language=self.parent.translation.language,
        )
        destination = Project.objects.create(name="Destination", slug="destination")
        self.create_po_new_base(name="Destination component", project=destination)
        pid_queue: Queue[int] = Queue()

        def delete() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid_queue.put(cursor.fetchone()[0])
            WorkflowSetting.objects.filter(pk=workflow.pk).delete()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with source_project_gate([self.component.project_id], exclusive=True):
                future = executor.submit(connected, delete)
                self.wait_for_blocked(pid_queue.get(timeout=10))
                workflow.project = destination
                workflow.save()
            with self.assertRaisesMessage(
                ValidationError, "Workflow project changed concurrently"
            ):
                future.result(timeout=15)
        workflow.refresh_from_db()
        self.assertEqual(workflow.project_id, destination.pk)
        WorkflowSetting.objects.filter(pk=workflow.pk).delete()
        self.assertFalse(WorkflowSetting.objects.filter(pk=workflow.pk).exists())

    def test_child_edit_rechecks_source_after_waiting_for_row_lock(self) -> None:
        WorkflowSetting.objects.create(
            project=self.component.project,
            language=self.child.translation.language,
            source_language=self.parent.translation.language,
        )
        self.child.refresh_from_db()
        self.child.translate(None, "Accepted target", STATE_TRANSLATED, propagate=False)
        stale = Unit.objects.get(pk=self.child.pk)
        submitted_hash = stale.edit_content_hash
        pid_queue: Queue[int] = Queue()

        def edit() -> None:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid_queue.put(cursor.fetchone()[0])
            stale.translate(
                None,
                "Obsolete target",
                STATE_TRANSLATED,
                propagate=False,
                expected_source_hash=submitted_hash,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                self.parent.translate(
                    None, "New parent", STATE_TRANSLATED, propagate=False
                )
                future = executor.submit(connected, edit)
                self.wait_for_blocked(pid_queue.get(timeout=10))
            with self.assertRaisesMessage(
                ValidationError, "The source string has changed meanwhile"
            ):
                future.result(timeout=15)
        self.child.refresh_from_db()
        self.assertEqual(self.child.target, stale.target)
        self.assertEqual(self.child.state, STATE_NEEDS_REWRITING)
        self.assert_source_consistent(configured=True)

    def test_component_source_change_waits_for_parent_edit(self) -> None:
        WorkflowSetting.objects.create(
            project=self.component.project,
            language=self.child.translation.language,
            source_language=self.parent.translation.language,
        )
        pid_queue: Queue[int] = Queue()

        def change_component() -> None:
            component = Component.objects.get(pk=self.component.pk)
            component.source_language_id = self.parent.translation.language_id
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid_queue.put(cursor.fetchone()[0])
            component.save(update_fields=["source_language"])

        with ThreadPoolExecutor(max_workers=1) as executor:
            with source_operation(self.component):
                future = executor.submit(connected, change_component)
                self.wait_for_blocked(pid_queue.get(timeout=10))
                self.parent.target = "Edited parent"
                self.parent.save()
            future.result(timeout=15)
        self.assert_source_consistent(configured=False)

    def test_concurrent_workflow_creation_rejects_duplicate(self) -> None:
        ready = Barrier(2)
        results: Queue[bool] = Queue()

        def create() -> None:
            ready.wait(timeout=10)
            try:
                WorkflowSetting.objects.create(
                    project_id=self.component.project_id,
                    language_id=self.child.translation.language_id,
                    source_language_id=self.parent.translation.language_id,
                )
            except ValidationError:
                results.put(False)
            else:
                results.put(True)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(connected, create)
            second = executor.submit(connected, create)
            first.result(timeout=15)
            second.result(timeout=15)
        self.assertEqual(
            sorted([results.get_nowait(), results.get_nowait()]), [False, True]
        )
        self.assertEqual(
            WorkflowSetting.objects.filter(project=self.component.project).count(), 1
        )
        self.assert_source_consistent(configured=True)

    def test_rollback_restores_workflow_view(self) -> None:
        with source_project_gate([self.component.project_id], exclusive=True):
            with (
                self.assertRaisesMessage(ValueError, "rollback"),
                source_project_gate([self.component.project_id], exclusive=True),
            ):
                WorkflowSetting.objects.create(
                    project=self.component.project,
                    language=self.child.translation.language,
                    source_language=self.parent.translation.language,
                )
                self.assertTrue(source_workflows(self.component.project_id))
                msg = "rollback"
                raise ValueError(msg)
            self.assertEqual(source_workflows(self.component.project_id), {})
            self.assertFalse(
                WorkflowSetting.objects.filter(project=self.component.project).exists()
            )
        self.assert_source_consistent(configured=False)
        self.assertFalse(self.component.project.translation_parent_language_ids)

    @staticmethod
    def migrate_to_latest() -> None:
        """Restore the full schema so later migrations stay applied."""
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_source_migrations_preserve_existing_data(self) -> None:
        previous = [("trans", "0111_component_pull_request_url")]
        before = list(Unit.objects.order_by("pk").values_list("pk", "state", "details"))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            workflow = apps.get_model("trans", "WorkflowSetting").objects.create(
                project_id=self.component.project_id,
                language_id=self.child.translation.language_id,
                translation_review=True,
            )
        finally:
            self.migrate_to_latest()

        workflow = WorkflowSetting.objects.get(pk=workflow.pk)
        self.assertTrue(workflow.translation_review)
        self.assertIsNone(workflow.source_language_id)
        self.assertFalse(Unit.objects.filter(translation_parent__isnull=False).exists())
        self.assertEqual(
            before,
            list(Unit.objects.order_by("pk").values_list("pk", "state", "details")),
        )
        with source_project_gate([self.component.project_id]):
            self.assertEqual(source_workflows(self.component.project_id), {})

    def test_gate_migration_preserves_existing_data(self) -> None:
        workflow = WorkflowSetting.objects.create(
            project=self.component.project,
            language=self.child.translation.language,
            source_language=self.parent.translation.language,
        )
        before = list(Unit.objects.order_by("pk").values_list("pk", "state", "details"))
        try:
            MigrationExecutor(connection).migrate(
                [("trans", "0112_translation_parent")]
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regprocedure('weblate_source_workflow_gate(bigint,boolean)')"
                )
                self.assertIsNone(cursor.fetchone()[0])
        finally:
            self.migrate_to_latest()
        self.assertEqual(
            before,
            list(Unit.objects.order_by("pk").values_list("pk", "state", "details")),
        )
        with source_project_gate([self.component.project_id]):
            self.assertEqual(
                source_workflows(self.component.project_id),
                {workflow.language_id: workflow.source_language_id},
            )
