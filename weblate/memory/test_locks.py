# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from time import monotonic, sleep
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Q
from django.db.models.deletion import Collector
from django.test import TransactionTestCase

from weblate.lang.models import Language
from weblate.memory.models import Memory, MemoryScope, MemoryScopeMigrationState
from weblate.memory.tasks import (
    MEMORY_COMPONENT_BACKFILL_STATE,
    _attribute_memory_scope_components,
    attribute_memory_scope_queryset,
    backfill_memory_scope_components,
)
from weblate.trans.tests.utils import RepoTestMixin, clear_users_cache

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future


class BaseMemoryLockTest(TransactionTestCase):
    def setUp(self) -> None:
        Language.objects.flush_object_cache()
        self.addCleanup(Language.objects.flush_object_cache)
        super().setUp()

    def create_memory(self) -> Memory:
        memory = Memory(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Memory lock source",
            target="Memory lock target",
            origin="project/component",
        )
        Memory.objects.bulk_create([memory])
        return memory

    def wait_for_blocked(self, pid: int) -> None:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
                if cursor.fetchone()[0]:
                    return
            sleep(0.01)
        self.fail("The competing operation did not wait for the parent lock")

    def connected(self, action: Callable[[], None], pids: Queue[int]) -> None:
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.put(cursor.fetchone()[0])
                action()
        finally:
            connection.close()


class MemoryScopeLockTest(BaseMemoryLockTest):
    def test_cleanup_rechecks_original_filter_after_lock_wait(self) -> None:
        memory = self.create_memory()
        scope = MemoryScope.objects.create(
            memory=memory, scope=MemoryScope.SCOPE_SHARED
        )
        pids: Queue[int] = Queue()

        def remove() -> None:
            Memory.objects.filter(pk=memory.pk, origin=memory.origin).delete_scope(
                Q(scope=MemoryScope.SCOPE_SHARED), delete_legacy=False
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                Memory.objects.select_for_update().get(pk=memory.pk)
                future = executor.submit(self.connected, remove, pids)
                self.wait_for_blocked(pids.get(timeout=5))
                Memory.objects.filter(pk=memory.pk).update(origin="project/moved")
            future.result(timeout=10)
        self.assertTrue(MemoryScope.objects.filter(pk=scope.pk).exists())

    def test_cleanup_rechecks_scopes_after_parent_lock_wait(self) -> None:
        memory = self.create_memory()
        MemoryScope.objects.create(memory=memory, scope=MemoryScope.SCOPE_SHARED)
        pids: Queue[int] = Queue()

        def remove_shared() -> None:
            Memory.objects.filter(pk=memory.pk).delete_scope(
                Q(scope=MemoryScope.SCOPE_SHARED), delete_legacy=False
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                retained = MemoryScope.objects.create(
                    memory=memory, scope=MemoryScope.SCOPE_GLOBAL_FILE
                )
                # Exercise the FK lock held by an insert before it commits.
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                future = executor.submit(self.connected, remove_shared, pids)
                self.wait_for_blocked(pids.get(timeout=5))
            future.result(timeout=10)
        self.assertTrue(Memory.objects.filter(pk=memory.pk).exists())
        self.assertTrue(MemoryScope.objects.filter(pk=retained.pk).exists())
        self.assertFalse(memory.scopes.filter(scope=MemoryScope.SCOPE_SHARED).exists())

    def test_cleanup_blocks_new_references_before_cascade(self) -> None:
        memory = self.create_memory()
        MemoryScope.objects.create(memory=memory, scope=MemoryScope.SCOPE_SHARED)
        pids: Queue[int] = Queue()
        futures: list[Future[None]] = []
        original = Collector.delete

        def insert() -> None:
            MemoryScope.objects.create(
                memory_id=memory.pk, scope=MemoryScope.SCOPE_GLOBAL_FILE
            )

        with ThreadPoolExecutor(max_workers=1) as executor:

            def delete(collector: Collector) -> tuple[int, dict[str, int]]:
                if Memory in collector.data:
                    futures.append(executor.submit(self.connected, insert, pids))
                    self.wait_for_blocked(pids.get(timeout=5))
                return original(collector)

            with patch.object(Collector, "delete", delete):
                Memory.objects.filter(pk=memory.pk).delete_scope(
                    Q(scope=MemoryScope.SCOPE_SHARED), delete_legacy=False
                )
            self.assertEqual(len(futures), 1)
            with self.assertRaises(IntegrityError):
                futures[0].result(timeout=10)
        self.assertFalse(Memory.objects.filter(pk=memory.pk).exists())

    def test_delete_scope_rolls_back_earlier_batches(self) -> None:
        memories = [self.create_memory(), self.create_memory()]
        scopes = [
            MemoryScope.objects.create(memory=memory, scope=MemoryScope.SCOPE_SHARED)
            for memory in memories
        ]
        original = Collector.delete
        deleted = 0

        def delete(collector: Collector) -> tuple[int, dict[str, int]]:
            nonlocal deleted
            if Memory in collector.data:
                deleted += 1
                if deleted == 2:
                    msg = "Interrupted cleanup"
                    raise RuntimeError(msg)
            return original(collector)

        with (
            patch("weblate.memory.models.MEMORY_SCOPE_DELETE_BATCH_SIZE", 1),
            patch.object(Collector, "delete", delete),
            self.assertRaisesMessage(RuntimeError, "Interrupted cleanup"),
        ):
            Memory.objects.filter(
                pk__in=[memory.pk for memory in memories]
            ).delete_scope(Q(scope=MemoryScope.SCOPE_SHARED), delete_legacy=False)
        self.assertEqual(
            MemoryScope.objects.filter(pk__in=[s.pk for s in scopes]).count(), 2
        )
        self.assertEqual(
            Memory.objects.filter(pk__in=[m.pk for m in memories]).count(), 2
        )


class MemoryAttributionLockTest(RepoTestMixin, BaseMemoryLockTest):
    def setUp(self) -> None:
        clear_users_cache()
        self.addCleanup(clear_users_cache)
        self.clone_test_repos()
        super().setUp()
        self.component = self.create_component()

    def test_cleanup_and_attribution_use_parent_first_lock_order(self) -> None:
        for backfill in (False, True):
            for retain_parent in (False, True):
                with self.subTest(backfill=backfill, retain_parent=retain_parent):
                    self.assert_cleanup_overlap(
                        backfill=backfill, retain_parent=retain_parent
                    )

    def assert_cleanup_overlap(self, *, backfill: bool, retain_parent: bool) -> None:
        memory = self.create_memory()
        shared = MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.component.project,
        )
        retained = (
            MemoryScope.objects.create(
                memory=memory, scope=MemoryScope.SCOPE_GLOBAL_FILE
            )
            if retain_parent
            else None
        )
        following_memory = self.create_memory()
        Memory.objects.filter(pk=following_memory.pk).update(
            origin=self.component.full_slug
        )
        following = MemoryScope.objects.create(
            memory=following_memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.component.project,
        )
        MemoryScopeMigrationState.objects.filter(
            name=MEMORY_COMPONENT_BACKFILL_STATE
        ).delete()
        parent_locked = Event()
        release_cleanup = Event()
        cleanup_pids: Queue[int] = Queue()
        attribution_pids: Queue[int] = Queue()

        def intercept(
            execute: Callable[..., object],
            sql: str,
            params: object,
            many: bool,
            context: object,
        ) -> object:
            result = execute(sql, params, many, context)
            if 'FOR UPDATE OF "memory_memory"' in sql:
                parent_locked.set()
                if not release_cleanup.wait(10):
                    msg = "Cleanup was not released"
                    raise TimeoutError(msg)
            return result

        def cleanup() -> None:
            with connection.execute_wrapper(intercept):
                Memory.objects.filter(pk=memory.pk).delete_scope(
                    Q(scope=MemoryScope.SCOPE_SHARED), delete_legacy=False
                )

        def attribute() -> None:
            if backfill:
                backfill_memory_scope_components(batch_size=1)
            else:
                attribute_memory_scope_queryset(
                    MemoryScope.objects.filter(pk__in=[shared.pk, following.pk]),
                    batch_size=1,
                )

        with (
            patch(
                "weblate.memory.tasks.backfill_memory_scope_components.delay"
            ) as queued,
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(self.connected, cleanup, cleanup_pids)
            try:
                self.assertTrue(parent_locked.wait(5))
                second = executor.submit(self.connected, attribute, attribution_pids)
                self.wait_for_blocked(attribution_pids.get(timeout=5))
                # Attribution must wait for the parent without holding its scope.
                with transaction.atomic():
                    MemoryScope.objects.select_for_update(nowait=True).get(pk=shared.pk)
            finally:
                release_cleanup.set()
                first.result(timeout=10)
            second.result(timeout=10)
            if backfill:
                queued.assert_called_once_with(batch_size=1)
                state = MemoryScopeMigrationState.objects.get(
                    name=MEMORY_COMPONENT_BACKFILL_STATE
                )
                self.assertEqual(state.last_memory_id, shared.pk)
                self.assertFalse(state.completed)
                backfill_memory_scope_components(batch_size=1)
        following.refresh_from_db()
        self.assertEqual(following.source_component_id, self.component.pk)
        self.assertFalse(MemoryScope.objects.filter(pk=shared.pk).exists())
        self.assertEqual(Memory.objects.filter(pk=memory.pk).exists(), retain_parent)
        if retained is not None:
            self.assertTrue(MemoryScope.objects.filter(pk=retained.pk).exists())

    def test_attribution_rechecks_selection_after_parent_lock_wait(self) -> None:
        for backfill in (False, True):
            with self.subTest(backfill=backfill):
                self.assert_selection_rechecked(backfill=backfill)

    def assert_selection_rechecked(self, *, backfill: bool) -> None:
        memory = self.create_memory()
        scope = MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.component.project,
        )
        MemoryScopeMigrationState.objects.filter(
            name=MEMORY_COMPONENT_BACKFILL_STATE
        ).delete()
        pids: Queue[int] = Queue()

        def attribute() -> None:
            if backfill:
                backfill_memory_scope_components()
            else:
                attribute_memory_scope_queryset(
                    MemoryScope.objects.filter(
                        pk=scope.pk, source_component__isnull=True
                    )
                )

        with (
            patch(
                "weblate.memory.tasks._attribute_memory_scope_components"
            ) as attributed,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            with transaction.atomic():
                Memory.objects.select_for_update().get(pk=memory.pk)
                future = executor.submit(self.connected, attribute, pids)
                self.wait_for_blocked(pids.get(timeout=5))
                MemoryScope.objects.filter(pk=scope.pk).update(
                    source_component=self.component
                )
            future.result(timeout=10)
            attributed.assert_not_called()
        scope.refresh_from_db()
        self.assertEqual(scope.source_component_id, self.component.pk)

    def test_restricted_attribution_upgrades_parent_lock_before_cleanup(self) -> None:
        from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        memory = self.create_memory()
        Memory.objects.filter(pk=memory.pk).update(origin=self.component.full_slug)
        scope = MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.component.project,
        )
        original = Collector.delete
        probed = False
        pids: Queue[int] = Queue()

        def probe() -> None:
            with (
                self.assertRaisesMessage(OperationalError, "could not obtain lock"),
                transaction.atomic(),
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SELECT id FROM memory_memory WHERE id = %s FOR KEY SHARE NOWAIT",
                    [memory.pk],
                )

        def delete(collector: Collector) -> tuple[int, dict[str, int]]:
            nonlocal probed
            if Memory in collector.data:
                probed = True
                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(self.connected, probe, pids).result(timeout=10)
            return original(collector)

        with patch.object(Collector, "delete", delete):
            attribute_memory_scope_queryset(MemoryScope.objects.filter(pk=scope.pk))
        self.assertTrue(probed)
        self.assertFalse(Memory.objects.filter(pk=memory.pk).exists())

    def test_attribution_keeps_parent_stable_and_allows_new_scopes(self) -> None:
        for backfill in (False, True):
            with self.subTest(backfill=backfill):
                self.assert_attribution_locks(backfill=backfill)

    def assert_attribution_locks(self, *, backfill: bool) -> None:
        memory = self.create_memory()
        Memory.objects.filter(pk=memory.pk).update(origin=self.component.full_slug)
        scope = MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.component.project,
        )
        MemoryScopeMigrationState.objects.filter(
            name=MEMORY_COMPONENT_BACKFILL_STATE
        ).delete()
        pids: Queue[int] = Queue()

        def probe() -> None:
            with (
                self.assertRaisesMessage(OperationalError, "could not obtain lock"),
                transaction.atomic(),
            ):
                Memory.objects.select_for_update(nowait=True).get(pk=memory.pk)
            with (
                self.assertRaisesMessage(OperationalError, "could not obtain lock"),
                transaction.atomic(),
            ):
                MemoryScope.objects.select_for_update(nowait=True).get(pk=scope.pk)
            MemoryScope.objects.create(
                memory_id=memory.pk, scope=MemoryScope.SCOPE_GLOBAL_FILE
            )

        def attribute(scopes: list[MemoryScope]) -> None:
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(self.connected, probe, pids).result(timeout=10)
            _attribute_memory_scope_components(scopes)

        with patch(
            "weblate.memory.tasks._attribute_memory_scope_components",
            side_effect=attribute,
        ):
            if backfill:
                backfill_memory_scope_components()
            else:
                attribute_memory_scope_queryset(MemoryScope.objects.filter(pk=scope.pk))
        scope.refresh_from_db()
        self.assertEqual(scope.source_component_id, self.component.pk)
        self.assertTrue(
            memory.scopes.filter(scope=MemoryScope.SCOPE_GLOBAL_FILE).exists()
        )
