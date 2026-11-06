# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for unitdata models."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse
from django.utils.html import format_html

from weblate.automation.context import automation_origin
from weblate.checks.base import BatchCheckMixin, TargetCheck
from weblate.checks.consistency import ConsistencyCheck
from weblate.checks.locks import (
    check_boundary_lock,
    check_component_session_read_lock,
    check_project_read_lock,
    check_project_session_read_lock,
    lock_check_projects,
)
from weblate.checks.models import CHECKS, Check
from weblate.checks.tasks import (
    coalesce_component_check_batches,
    finalize_component_checks,
    refresh_propagated_checks,
    schedule_component_check_batch,
)
from weblate.trans.models import Component, Project, Unit
from weblate.trans.tasks import auto_translate
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin, get_test_actor
from weblate.trans.util import join_plural
from weblate.utils.change_origin import (
    acting_user_context,
    change_origin,
    get_acting_user,
    get_change_origin,
)
from weblate.utils.lock import WeblateLock
from weblate.utils.state import STATE_TRANSLATED
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from types import TracebackType

    from weblate.utils.change_origin import ChangeOrigin


class CheckBoundaryLockTest(TransactionTestCase):
    def test_transaction_writer_finishes_before_transition(self) -> None:
        entered = Event()
        release = Event()
        attempted = Event()
        acquired = Event()

        def writer() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    lock_check_projects({123456}, exclusive=False)
                    entered.set()
                    if not release.wait(10):
                        msg = "Writer was not released"
                        raise TimeoutError(msg)
            finally:
                close_old_connections()

        def transition() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    attempted.set()
                    lock_check_projects({123456}, exclusive=True)
                    acquired.set()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer_result = pool.submit(writer)
            self.assertTrue(entered.wait(10))
            transition_result = pool.submit(transition)
            self.assertTrue(attempted.wait(10))
            self.assertFalse(acquired.wait(0.1))
            release.set()
            writer_result.result(timeout=10)
            transition_result.result(timeout=10)
        self.assertTrue(acquired.is_set())

    def test_chunked_worker_finishes_before_transition(self) -> None:
        attempted = Event()
        acquired = Event()

        def transition() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    attempted.set()
                    lock_check_projects({123457}, exclusive=True)
                    acquired.set()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with check_project_session_read_lock(123457):
                result = pool.submit(transition)
                self.assertTrue(attempted.wait(10))
                self.assertFalse(acquired.wait(0.1))
            result.result(timeout=10)
        self.assertTrue(acquired.is_set())

    def test_workspace_worker_blocks_other_project_boundary_change(self) -> None:
        actor = get_test_actor(self)
        with acting_user_context(actor):
            workspace = Workspace.objects.create(
                name="Shared checks", propagation_scope="workspace"
            )
            first = Project.objects.create(
                name="First", slug="first", workspace=workspace
            )
            second = Project.objects.create(
                name="Second", slug="second", workspace=workspace
            )
        attempted = Event()
        acquired = Event()

        def transition() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    attempted.set()
                    lock_check_projects({second.pk}, exclusive=True)
                    acquired.set()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with check_project_session_read_lock(first.pk):
                result = pool.submit(transition)
                self.assertTrue(attempted.wait(10))
                self.assertFalse(acquired.wait(0.1))
            result.result(timeout=10)
        self.assertTrue(acquired.is_set())

    def test_writer_waits_for_committed_transition(self) -> None:
        attempted = Event()
        acquired = Event()

        def writer() -> None:
            close_old_connections()
            try:
                with transaction.atomic():
                    attempted.set()
                    lock_check_projects({123458}, exclusive=False)
                    acquired.set()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                lock_check_projects({123458}, exclusive=True)
                result = pool.submit(writer)
                self.assertTrue(attempted.wait(10))
                self.assertFalse(acquired.wait(0.1))
            result.result(timeout=10)
        self.assertTrue(acquired.is_set())


class CheckFinalizationConcurrencyTest(RepoTestMixin, TransactionTestCase):
    def setUp(self) -> None:
        self.clone_test_repos()
        super().setUp()
        self.component = self.create_component()
        self.other = self.create_po(name="Other", project=self.component.project)
        self.unit = Unit.objects.get(
            translation__component=self.component,
            translation__language__code="cs",
            source="Hello, world!\n",
        )

    def run_finalizer(self, component_id: int) -> None:
        close_old_connections()
        try:
            finalize_component_checks(
                component_id, [], ["inconsistent", "reused"], batch_mode=True
            )
        finally:
            connection.close()

    def test_inline_checks_run_outside_editing_transaction(self) -> None:
        def finalize(*args: object, **kwargs: object) -> None:
            self.assertFalse(connection.in_atomic_block)

        with patch(
            "weblate.checks.tasks.finalize_component_checks", side_effect=finalize
        ) as callback:
            with transaction.atomic():
                self.component.start_batched_checks()
                self.component.batched_checks.add("inconsistent")
                self.component.run_batched_checks()
                callback.assert_not_called()
            callback.assert_called_once()

    def test_batches_keep_boundary_locked_until_commit(self) -> None:
        for workspace_scope in (False, True):
            with self.subTest(workspace_scope=workspace_scope):
                if workspace_scope:
                    workspace = Workspace.objects.create(
                        name="Concurrent checks", propagation_scope="workspace"
                    )
                    Project.objects.filter(pk=self.component.project_id).update(
                        workspace=workspace
                    )
                    other_project = self.create_project(
                        name="Other project", slug="other-project", workspace=workspace
                    )
                    Component.objects.filter(pk=self.other.pk).update(
                        project=other_project
                    )
                self.assert_finalizers_serialize()

    def assert_finalizers_serialize(self) -> None:
        first_written = Event()
        second_attempted = Event()
        second_entered = Event()
        first_committed = Event()
        original_enter = WeblateLock.__enter__
        original_exit = WeblateLock.__exit__
        Check.objects.filter(unit=self.unit, name="inconsistent").delete()

        def enter(lock) -> None:
            if (
                lock.scope in {"project:checks", "workspace:checks"}
                and first_written.is_set()
                and not first_committed.is_set()
            ):
                second_attempted.set()
            original_enter(lock)

        def exit_lock(
            lock: WeblateLock,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            original_exit(lock, exc_type, exc_value, traceback)
            if (
                lock.scope in {"project:checks", "workspace:checks"}
                and not lock.is_locked
            ):
                self.assertFalse(connection.in_atomic_block)

        def perform(check, component) -> None:
            if component.pk == self.component.pk:
                if not first_written.is_set():
                    Check.objects.create(unit_id=self.unit.pk, name="inconsistent")
                    transaction.on_commit(first_committed.set)
                    first_written.set()
                    self.assertTrue(second_attempted.wait(10))
                else:
                    self.assertFalse(second_entered.wait(0.1))
            else:
                second_entered.set()
                self.assertTrue(first_committed.is_set())
                self.assertTrue(
                    Check.objects.filter(
                        unit_id=self.unit.pk, name="inconsistent"
                    ).exists()
                )

        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(WeblateLock, "__enter__", enter),
            patch.object(WeblateLock, "__exit__", exit_lock),
            patch.object(BatchCheckMixin, "_perform_batch", perform),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(self.run_finalizer, self.component.pk)
            self.assertTrue(first_written.wait(10))
            second = pool.submit(self.run_finalizer, self.other.pk)
            first.result(timeout=15)
            second.result(timeout=15)
        self.assertTrue(second_entered.is_set())

    def test_boundary_wait_does_not_hold_component_lock(self) -> None:
        attempted = Event()
        original_enter = WeblateLock.__enter__

        def enter(lock) -> None:
            if lock.scope == "project:checks":
                attempted.set()
            original_enter(lock)

        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(WeblateLock, "__enter__", enter),
            patch.object(BatchCheckMixin, "_perform_batch"),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            with check_boundary_lock(self.component.project):
                attempted.clear()
                result = pool.submit(self.run_finalizer, self.component.pk)
                self.assertTrue(attempted.wait(10))
                with self.component.checks_lock:
                    pass
            result.result(timeout=10)

    def test_eager_refresh_reuses_boundary_lock_after_commit(self) -> None:
        def perform(check, component) -> None:
            if check.check_id == "inconsistent":
                transaction.on_commit(
                    lambda: refresh_propagated_checks(component.project_id, [])
                )

        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(BatchCheckMixin, "_perform_batch", perform),
            patch("weblate.checks.tasks._refresh_propagated_checks") as refresh,
        ):
            self.run_finalizer(self.component.pk)
        refresh.assert_called_once()

    def test_propagated_refresh_waits_for_finalization_boundary(self) -> None:
        attempted = Event()
        entered = Event()
        original_enter = WeblateLock.__enter__

        def enter(lock) -> None:
            if lock.scope == "project:checks":
                attempted.set()
            original_enter(lock)

        def refresh() -> None:
            close_old_connections()
            try:
                refresh_propagated_checks(self.component.project_id, [])
            finally:
                connection.close()

        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(WeblateLock, "__enter__", enter),
            patch(
                "weblate.checks.tasks._refresh_propagated_checks",
                side_effect=lambda *_args: entered.set(),
            ),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            with check_boundary_lock(self.component.project):
                attempted.clear()
                result = pool.submit(refresh)
                self.assertTrue(attempted.wait(10))
                self.assertFalse(entered.wait(0.1))
            result.result(timeout=10)
        self.assertTrue(entered.is_set())

    def test_unrelated_project_proceeds_while_boundary_is_locked(self) -> None:
        other_project = self.create_project(name="Independent", slug="independent")
        Component.objects.filter(pk=self.other.pk).update(project=other_project)
        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            patch.object(BatchCheckMixin, "_perform_batch"),
            ThreadPoolExecutor(max_workers=1) as pool,
            check_boundary_lock(self.component.project),
        ):
            pool.submit(self.run_finalizer, self.other.pk).result(timeout=10)


class CheckBoundaryRefreshTest(FixtureTestCase):
    def test_finalizer_selects_boundary_lock_after_refresh(self) -> None:
        for propagation, units, checks, expected in (
            (True, [123], [], True),
            (True, [], ["inconsistent"], True),
            (True, [], ["long_untranslated"], False),
            (False, [123], ["inconsistent"], False),
        ):
            with self.subTest(propagation=propagation, units=units, checks=checks):
                Component.objects.filter(pk=self.component.pk).update(
                    allow_translation_propagation=propagation
                )

                def run(
                    component: Component,
                    unit_ids: list[int],
                    *,
                    expected_lock: bool = expected,
                    expected_units: tuple[int, ...] = tuple(units),
                ) -> None:
                    self.assertEqual(
                        component.project.checks_lock.is_locked, expected_lock
                    )
                    self.assertEqual(tuple(unit_ids), expected_units)

                with patch(
                    "weblate.checks.tasks._run_component_checks", side_effect=run
                ):
                    finalize_component_checks(
                        self.component.pk, units, checks, batch_mode=True
                    )

    def test_finalizer_restores_state_and_releases_locks_after_error(self) -> None:
        self.component.refresh_peer_source_checks = False
        with (
            patch(
                "weblate.checks.tasks._run_component_checks",
                side_effect=ValueError("Failed"),
            ),
            self.assertRaisesMessage(ValueError, "Failed"),
        ):
            finalize_component_checks(
                self.component.pk,
                [],
                ["inconsistent"],
                batch_mode=True,
                component=self.component,
                refresh_source_checks=True,
            )
        self.assertFalse(self.component.batch_checks)
        self.assertEqual(self.component.batched_checks, set())
        self.assertFalse(self.component.refresh_peer_source_checks)
        self.assertFalse(self.component.checks_lock.is_locked)
        self.assertFalse(self.component.project.checks_lock.is_locked)

    def test_finalizer_handles_component_deleted_before_guard(self) -> None:
        with patch(
            "weblate.checks.locks.check_project_session_read_lock",
            side_effect=Component.DoesNotExist,
        ):
            finalize_component_checks(
                self.component.pk, [], ["inconsistent"], batch_mode=True
            )

    def test_nested_workspace_lock_reuses_lock_across_projects(self) -> None:
        workspace = Workspace.objects.create(
            name="Shared boundary", propagation_scope="workspace"
        )
        projects = [
            Project(pk=identifier, workspace=workspace, name="Shared", slug="shared")
            for identifier in (1, 2)
        ]
        with (
            TemporaryDirectory() as directory,
            self.settings(DATA_DIR=directory),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            check_boundary_lock(projects[0]),
            check_boundary_lock(projects[1]),
        ):
            pass
        # A leaked registry entry would try to reuse the previous deleted file.
        with (
            TemporaryDirectory() as directory,
            self.settings(DATA_DIR=directory),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
            check_boundary_lock(projects[1]),
        ):
            pass

    def test_nested_redis_lock_released_after_error(self) -> None:
        redis_lock = MagicMock()
        redis_lock.owned.return_value = False
        project = Project(pk=123, name="Shared", slug="shared")
        other = Project(pk=123, name="Shared", slug="shared")
        with (
            patch("weblate.utils.lock.is_redis_cache", return_value=True),
            patch(
                "weblate.utils.lock.cache",
                SimpleNamespace(lock=MagicMock(return_value=redis_lock)),
            ),
        ):
            with (
                self.assertRaisesMessage(ValueError, "Failed"),
                check_boundary_lock(project),
                check_boundary_lock(other),
            ):
                msg = "Failed"
                raise ValueError(msg)
            self.assertEqual(redis_lock.acquire.call_count, 1)
            redis_lock.release.assert_called_once()
            with check_boundary_lock(other):
                pass
            self.assertEqual(redis_lock.acquire.call_count, 2)
            self.assertEqual(redis_lock.release.call_count, 2)

    def test_inline_component_batch_waits_for_commit_and_preserves_context(
        self,
    ) -> None:
        actor = get_test_actor(self)
        origin: ChangeOrigin = {"scope": "repository"}
        observed = []

        def finalize(*args: object, **kwargs: object) -> None:
            observed.append((get_acting_user(), get_change_origin()))

        with (
            patch(
                "weblate.checks.tasks.finalize_component_checks", side_effect=finalize
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            with acting_user_context(actor):
                token = change_origin.set(origin)
                try:
                    self.component.start_batched_checks()
                    self.component.batched_checks.add("inconsistent")
                    self.component.run_batched_checks()
                finally:
                    change_origin.reset(token)
            self.assertEqual(observed, [])
        self.assertEqual(observed, [(actor, origin)])

    def test_automation_batch_preserves_automation_context_after_commit(self) -> None:
        observed = []

        def finalize(*args: object, **kwargs: object) -> None:
            observed.append(automation_origin.get())

        with (
            self.settings(CELERY_TASK_ALWAYS_EAGER=False),
            patch(
                "weblate.checks.tasks.finalize_component_checks", side_effect=finalize
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            token = automation_origin.set(123)
            try:
                self.component.start_batched_checks()
                self.component.batched_checks.add("inconsistent")
                self.component.run_batched_checks()
            finally:
                automation_origin.reset(token)
            self.assertEqual(observed, [])
        self.assertEqual(observed, [123])

    def test_coalesced_inline_batches_preserve_rollback_boundaries(self) -> None:
        with (
            patch("weblate.checks.tasks.finalize_component_checks") as finalize,
            self.captureOnCommitCallbacks(execute=True),
        ):
            with (
                transaction.atomic(),
                coalesce_component_check_batches(using="default"),
            ):
                schedule_component_check_batch(
                    self.component, set(), {"inconsistent"}, using="default"
                )
                with self.assertRaises(ValueError), transaction.atomic():
                    with coalesce_component_check_batches(using="default"):
                        schedule_component_check_batch(
                            self.component, set(), {"reused"}, using="default"
                        )
                    msg = "Rolled back"
                    raise ValueError(msg)
                schedule_component_check_batch(
                    self.component, set(), {"long_untranslated"}, using="default"
                )
            finalize.assert_not_called()
        finalize.assert_called_once()
        self.assertEqual(
            set(finalize.call_args.args[2]), {"inconsistent", "long_untranslated"}
        )

    def test_unchanged_boundary_preserves_shared_project(self) -> None:
        for lock in (check_project_read_lock, check_component_session_read_lock):
            with self.subTest(lock=lock.__name__):
                component = Component.objects.select_related("project__workspace").get(
                    pk=self.component.pk
                )
                project = component.project
                with lock(component):
                    self.assertIs(component.project, project)
                project.secondary_language = self.get_translation().language
                with acting_user_context(get_test_actor(self)):
                    project.save(update_fields=["secondary_language"])
                self.assertEqual(
                    component.project.secondary_language_id,
                    project.secondary_language_id,
                )

    def test_changed_boundary_refreshes_project(self) -> None:
        workspace = Workspace.objects.create(name="Check boundary workspace")
        Project.objects.filter(pk=self.project.pk).update(workspace=workspace)
        for lock in (check_project_read_lock, check_component_session_read_lock):
            with self.subTest(lock=lock.__name__):
                Workspace.objects.filter(pk=workspace.pk).update(
                    propagation_scope="project"
                )
                component = Component.objects.select_related("project__workspace").get(
                    pk=self.component.pk
                )
                original = component.project
                Workspace.objects.filter(pk=workspace.pk).update(
                    propagation_scope="workspace"
                )
                with lock(component):
                    self.assertIsNot(component.project, original)
                    current_workspace = component.project.workspace
                    assert current_workspace is not None
                    self.assertEqual(current_workspace.propagation_scope, "workspace")

    def test_changed_project_access_refreshes_project(self) -> None:
        for lock in (check_project_read_lock, check_component_session_read_lock):
            with self.subTest(lock=lock.__name__):
                Project.objects.filter(pk=self.project.pk).update(
                    access_control=Project.ACCESS_PUBLIC
                )
                component = Component.objects.select_related("project__workspace").get(
                    pk=self.component.pk
                )
                original = component.project
                Project.objects.filter(pk=self.project.pk).update(
                    access_control=Project.ACCESS_PRIVATE
                )
                with lock(component):
                    self.assertIsNot(component.project, original)
                    self.assertEqual(
                        component.project.access_control, Project.ACCESS_PRIVATE
                    )

    def test_component_move_refreshes_project(self) -> None:
        destination = self.create_project(
            name="Moved component", slug="moved-component"
        )
        for lock in (check_project_read_lock, check_component_session_read_lock):
            with self.subTest(lock=lock.__name__):
                Component.objects.filter(pk=self.component.pk).update(
                    project=self.project
                )
                component = Component.objects.select_related("project__workspace").get(
                    pk=self.component.pk
                )
                Component.objects.filter(pk=component.pk).update(project=destination)
                with lock(component):
                    self.assertEqual(component.project_id, destination.pk)
                    self.assertEqual(component.project.pk, destination.pk)


class CheckLintTestCase(SimpleTestCase):
    def test_plain_description(self) -> None:
        check = Check(name="same")
        for description, expected in (
            ("Plain <tag> &amp; text.", "Plain <tag> &amp; text."),
            (
                format_html("Use <code>{}</code>.", '<tag> & "quote"'),
                'Use <tag> & "quote".',
            ),
            (
                format_html(
                    "{}<br />{}<br>{}<BR/>{}", "First", "Second", "Third", "Fourth"
                ),
                "First\nSecond\nThird\nFourth",
            ),
            (
                format_html("<code>{}</code>", "<br />"),
                "<br />",
            ),
        ):
            with (
                self.subTest(description=description),
                patch.object(
                    check.check_obj, "get_description", return_value=description
                ),
            ):
                self.assertEqual(check.get_plain_description(), expected)

    def test_unknown_plain_description(self) -> None:
        self.assertEqual(Check(name="-unknown-").get_plain_description(), "-unknown-")

    def test_check_id(self) -> None:
        for check in CHECKS.values():
            self.assertRegex(check.check_id, r"^[a-z][a-z0-9_-]*[a-z]$")
            self.assertTrue(
                check.description.endswith("."),
                f"{check.__class__.__name__} description does not have a stop: {check.description}",
            )


class CheckTargetFastPathTest(SimpleTestCase):
    def test_custom_check_target_is_called(self) -> None:
        class CustomTargetCheck(TargetCheck):
            check_id = "custom"

            def check_target(self, sources, targets, unit) -> bool:
                unit.check_target_called = True
                return True

            def check_target_unit(self, sources, targets, unit) -> bool:
                msg = "check_target() override was bypassed"
                raise AssertionError(msg)

        unit: Any = SimpleNamespace(check_target_called=False)

        self.assertTrue(
            CustomTargetCheck().check_target_with_flags(
                ["source"], ["target"], unit, set()
            )
        )
        self.assertTrue(unit.check_target_called)


class CheckModelTestCase(FixtureTestCase):
    def test_wrapped_line_budget_is_visible_in_description(self) -> None:
        unit = self.get_unit()
        Unit.objects.filter(pk=unit.pk).update(
            target="word " * 1000, state=STATE_TRANSLATED, extra_flags="max-size:10:2"
        )
        unit = Unit.objects.get(pk=unit.pk)
        check, _created = Check.objects.get_or_create(unit=unit, name="max-size")
        self.assertTrue(
            check.check_obj.check_target_unit(
                unit.get_source_plurals(), unit.get_target_plurals(), unit
            )
        )
        description = str(check.get_description())
        self.assertIn("Font rendering limits exceeded", description)
        self.assertNotIn("<img", description)
        cache.clear()
        with patch("weblate.fonts.render.draw_text") as draw:
            description = str(check.get_description())
            self.assertIn("Font rendering limits exceeded", description)
            self.assertNotIn("<img", description)
            draw.assert_not_called()

    def test_render_does_not_hide_internal_value_errors(self) -> None:
        unit = self.get_unit()
        Unit.objects.filter(pk=unit.pk).update(extra_flags="max-size:200")
        Check.objects.get_or_create(unit=unit, name="max-size")
        url = reverse(
            "render-check", kwargs={"check_id": "max-size", "unit_id": unit.pk}
        )
        with (
            patch(
                "weblate.checks.render.check_render_size",
                side_effect=ValueError("renderer failed"),
            ),
            self.assertRaisesMessage(ValueError, "renderer failed"),
        ):
            self.client.get(url)

    def test_render_malformed_size_flag(self) -> None:
        target = self.get_unit()
        for unit in (target, target.source_unit):
            with self.subTest(source=unit.is_source):
                Unit.objects.filter(pk=unit.pk).update(extra_flags="max-size:invalid")
                Check.objects.get_or_create(unit=unit, name="max-size")
                url = reverse(
                    "render-check", kwargs={"check_id": "max-size", "unit_id": unit.pk}
                )
                with patch("weblate.fonts.render.get_font_properties") as font:
                    self.assertEqual(self.client.get(url).status_code, 404)
                    font.assert_not_called()

    def test_render_rejects_unattached_check(self) -> None:
        unit = self.get_unit()
        url = reverse(
            "render-check", kwargs={"check_id": "max-size", "unit_id": unit.pk}
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_render_budget_keeps_cached_previews(self) -> None:
        unit = self.get_unit()
        Unit.objects.filter(pk=unit.pk).update(extra_flags="max-size:24000:1000")
        unit = Unit.objects.get(pk=unit.pk)
        check = self.create_check("max-size")
        renderer = check.check_obj
        key = renderer.get_render_cache_key(unit, 0, unit.get_target_plurals()[0])
        cache.set(key, b"existing-preview")
        self.assertIn("<img", str(check.get_description()))
        url = reverse(
            "render-check", kwargs={"check_id": "max-size", "unit_id": unit.pk}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"existing-preview")
        cache.delete(key)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Font rendering limits exceeded", status_code=400)

    def create_check(self, name):
        return Check.objects.create(unit=self.get_unit(), name=name)

    def test_check(self) -> None:
        check = self.create_check("same")
        self.assertEqual(
            str(check.get_description()), "Source and translation are identical."
        )
        self.assertTrue(check.get_doc_url().endswith("user/checks.html#check-same"))
        self.assertEqual(str(check), "Unchanged translation")

    def test_check_nonexisting(self) -> None:
        check = self.create_check("-invalid-")
        self.assertEqual(check.get_description(), "-invalid-")
        self.assertEqual(check.get_doc_url(), "")

    def test_check_render(self) -> None:
        unit = self.get_unit()
        unit.source_unit.extra_flags = "max-size:1:1"
        unit.source_unit.save()
        check = self.create_check("max-size")
        url = reverse(
            "render-check", kwargs={"check_id": check.name, "unit_id": unit.id}
        )
        self.assertHTMLEqual(
            check.get_description(),
            format_html(
                '<a href="{0}?pos={1}" class="thumbnail img-check">'
                '<img class="img-fluid" src="{0}?pos={1}" /></a>',
                url,
                0,
            ),
        )
        self.assert_png(self.client.get(url))

    def test_source_check_render(self) -> None:
        unit = self.get_unit().source_unit
        Unit.objects.filter(pk=unit.pk).update(extra_flags="max-size:1:1")
        check = Check.objects.create(unit=unit, name="max-size")
        url = reverse(
            "render-check", kwargs={"check_id": check.name, "unit_id": unit.id}
        )
        self.assertHTMLEqual(
            check.get_description(),
            format_html(
                '<a href="{0}?pos={1}" class="thumbnail img-check">'
                '<img class="img-fluid" src="{0}?pos={1}" /></a>',
                url,
                0,
            ),
        )
        self.assert_png(self.client.get(url))

    def test_source_check_render_updates_after_source_change(self) -> None:
        cache.clear()
        unit = self.get_unit().source_unit
        Unit.objects.filter(pk=unit.pk).update(
            source="short", extra_flags="max-size:500"
        )
        url = reverse(
            "render-check", kwargs={"check_id": "max-size", "unit_id": unit.id}
        )

        response = self.client.get(url)
        self.assert_png(response)
        original = response.content

        Unit.objects.filter(pk=unit.pk).update(
            source="long " * 50, extra_flags="max-size:500"
        )
        response = self.client.get(url)
        self.assert_png(response)
        self.assertNotEqual(original, response.content)

    def test_source_check_render_later_plural_after_first_plural_failure(self) -> None:
        cache.clear()
        unit = self.get_unit().source_unit
        Unit.objects.filter(pk=unit.pk).update(
            source=join_plural(("long " * 50, "short")),
            extra_flags="max-size:500",
        )
        url = reverse(
            "render-check", kwargs={"check_id": "max-size", "unit_id": unit.id}
        )

        self.assert_png(self.client.get(f"{url}?pos=1"))

    def test_source_check_run_checks(self) -> None:
        unit = self.get_unit().source_unit
        Check.objects.filter(unit=unit, name="max-size").delete()
        unit.extra_flags = "max-size:500"
        unit.source = "long " * 50

        unit.run_checks()
        self.assertTrue(Check.objects.filter(unit=unit, name="max-size").exists())

        unit.source = "short"
        unit.check_cache = {}
        unit.run_checks()
        self.assertFalse(Check.objects.filter(unit=unit, name="max-size").exists())

    def test_check_order(self) -> None:
        unit = self.get_unit()
        Check.objects.filter(unit=unit).delete()
        for name in ("same", "end_newline", "begin_newline"):
            Check.objects.create(unit=unit, name=name)

        expected = ["begin_newline", "end_newline", "same"]
        self.assertEqual(
            list(
                Check.objects.filter(unit=unit).order().values_list("name", flat=True)
            ),
            expected,
        )
        self.assertEqual([check.name for check in unit.all_checks], expected)

        prefetched = Unit.objects.filter(pk=unit.pk).prefetch_all_checks().get()
        self.assertEqual([check.name for check in prefetched.all_checks], expected)


class BatchCheckMixinTest(SimpleTestCase):
    def test_project_checks_lock_uses_unique_file_name(self) -> None:
        project = Project(pk=1, name="Shared", slug="shared")

        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            project_lock = project.checks_lock
            component_lock = WeblateLock(
                scope="component:checks",
                key=1,
                slug=project.slug,
                timeout=5,
                origin=project.full_slug,
            )

        # ruff: ignore[private-member-access]
        self.assertNotEqual(project_lock._name, component_lock._name)
        # ruff: ignore[private-member-access]
        self.assertEqual(Path(project_lock._name).parent, Path(temp_dir, "locks"))
        self.assertEqual(
            # ruff: ignore[private-member-access]
            Path(project_lock._name).name,
            "project%3Achecks-1.lock",
        )
        self.assertEqual(
            # ruff: ignore[private-member-access]
            Path(component_lock._name).name,
            "component%3Achecks-1.lock",
        )

    def test_project_checks_lock_uses_longer_timeout(self) -> None:
        project = Project(name="Shared", slug="shared")

        with (
            TemporaryDirectory() as lock_path,
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            project.__dict__["full_path"] = lock_path
            project_lock = project.checks_lock

        # ruff: ignore[private-member-access]
        self.assertEqual(project_lock._timeout, 30)

    def test_component_checks_lock_uses_key_in_file_name(self) -> None:
        with (
            TemporaryDirectory() as temp_dir,
            self.settings(DATA_DIR=temp_dir),
            patch("weblate.utils.lock.is_redis_cache", return_value=False),
        ):
            first_lock = WeblateLock(
                scope="component:checks",
                key=1,
                slug="shared",
                timeout=5,
                origin="project/shared",
            )
            second_lock = WeblateLock(
                scope="component:checks",
                key=2,
                slug="shared",
                timeout=5,
                origin="project/shared",
            )

        # ruff: ignore[private-member-access]
        self.assertNotEqual(first_lock._name, second_lock._name)
        self.assertEqual(
            # ruff: ignore[private-member-access]
            Path(first_lock._name).name,
            "component%3Achecks-1.lock",
        )
        self.assertEqual(
            # ruff: ignore[private-member-access]
            Path(second_lock._name).name,
            "component%3Achecks-2.lock",
        )

    def test_project_wide_batch_uses_project_lock(self) -> None:
        project_lock = MagicMock()
        component: Any = SimpleNamespace(
            allow_translation_propagation=True,
            project=SimpleNamespace(propagation_checks_lock=project_lock),
        )

        with (
            patch.object(ConsistencyCheck, "_perform_batch") as perform_batch,
            patch(
                "weblate.checks.locks.check_component_session_read_lock"
            ) as boundary_lock,
        ):
            ConsistencyCheck().perform_batch(component)

        project_lock.__enter__.assert_called_once()
        project_lock.__exit__.assert_called_once()
        boundary_lock.assert_called_once_with(component)
        perform_batch.assert_called_once_with(component)

    def test_perform_batch_sorts_bulk_create_by_unique_key(self) -> None:
        class DummyBatchCheck(BatchCheckMixin):
            check_id = "dummy"

            def should_skip(self, unit) -> bool:
                return False

            def check_component(self, component):
                return [unit_b, unit_a]

        class FakeCheck:
            objects = MagicMock()

            def __init__(self, *, unit, dismissed, name) -> None:
                self.dismissed = dismissed
                self.name = name
                self.unit_id = unit.pk

        component: Any = SimpleNamespace(
            id=1,
            allow_translation_propagation=False,
            refresh_peer_source_checks=False,
            invalidate_cache=MagicMock(),
        )
        unit_a = SimpleNamespace(
            pk=2,
            all_checks_names=set(),
            translation=SimpleNamespace(component=component),
        )
        unit_b = SimpleNamespace(
            pk=1,
            all_checks_names=set(),
            translation=SimpleNamespace(component=component),
        )
        stale_checks = MagicMock()
        stale_checks.filter.return_value = stale_checks
        stale_checks.delete.return_value = (0, {})
        FakeCheck.objects.exclude.return_value = stale_checks

        with patch("weblate.checks.models.Check", FakeCheck):
            DummyBatchCheck().perform_batch(component)

        self.assertIsNotNone(FakeCheck.objects.bulk_create.call_args)
        created = FakeCheck.objects.bulk_create.call_args.args[0]
        self.assertEqual(
            [(check.unit_id, check.name) for check in created],
            [(1, "dummy"), (2, "dummy")],
        )


class BatchUpdateTest(ViewTestCase):
    """Test for complex manipulating translation."""

    def setUp(self) -> None:
        super().setUp()
        self.translation = self.get_translation()

    def do_base(self):
        # Single unit should have no consistency check
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

        # Add linked project
        with self.captureOnCommitCallbacks(execute=True):
            other = self.create_link_existing()

        # Now the inconsistent check should be there
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})
        return other

    def test_autotranslate(self) -> None:
        other = self.do_base()
        translation = other.translation_set.get(language_code="cs")
        with self.captureOnCommitCallbacks(execute=True):
            auto_translate(
                user_id=self.user.pk,
                enforce_permissions=False,
                mode="translate",
                q="state:<translated",
                auto_source="others",
                source_component_id=self.component.pk,
                engines=[],
                threshold=99,
                translation_id=translation.pk,
            )
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

    def test_noop(self) -> None:
        other = self.do_base()
        # The batch update should not remove it
        finalize_component_checks(
            self.component.id, [], ["inconsistent"], batch_mode=True
        )
        finalize_component_checks(other.id, [], ["inconsistent"], batch_mode=True)
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})

    def test_toggle(self) -> None:
        other = self.do_base()
        one_unit = self.get_unit()
        other_unit = Unit.objects.get(
            translation__language_code=one_unit.translation.language_code,
            translation__component=other,
            id_hash=one_unit.id_hash,
        )
        translated = one_unit.target

        combinations: tuple[tuple[str, str, set[str]], ...] = (
            (translated, "", {"inconsistent"}),
            ("", translated, {"inconsistent"}),
            ("", "", set()),
            (translated, translated, set()),
            ("", translated, {"inconsistent"}),
        )
        for update_one, update_other, expected in combinations:
            Unit.objects.filter(pk=one_unit.pk).update(target=update_one)
            Unit.objects.filter(pk=other_unit.pk).update(target=update_other)

            finalize_component_checks(
                self.component.id, [], ["inconsistent"], batch_mode=True
            )
            unit = self.get_unit()
            self.assertEqual(unit.all_checks_names, expected)

        for update_one, update_other, expected in combinations:
            Unit.objects.filter(pk=one_unit.pk).update(target=update_one)
            Unit.objects.filter(pk=other_unit.pk).update(target=update_other)

            finalize_component_checks(other.id, [], ["inconsistent"], batch_mode=True)
            unit = self.get_unit()
            self.assertEqual(unit.all_checks_names, expected)
