# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import time
from contextlib import contextmanager, nullcontext
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from celery.exceptions import Retry
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext, override_settings
from django.utils import timezone

from weblate.auth.models import User
from weblate.checks.tasks import finalize_component_checks
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import (
    Category,
    Component,
    PendingUnitChange,
    Project,
    Suggestion,
)
from weblate.trans.models.project import CommitPolicyChoices
from weblate.trans.repository import (
    RepositoryOperationConflictError,
    acquire_repository_operation,
    release_repository_operation,
)
from weblate.trans.repository_context import (
    RepositoryFollowupLockError,
    repository_task_deferred_auto_push,
    repository_task_deferred_background_tasks,
    repository_task_suppress_auto_push,
)
from weblate.trans.tasks import (
    RepositoryOperationRetryError,
    cleanup_repos,
    cleanup_stale_repos,
    cleanup_suggestions,
    commit_pending,
    component_alerts,
    daily_update_checks,
    execute_repository_operation,
    execute_repository_operation_method,
    perform_commit,
    perform_load,
    perform_push,
    perform_repository_operation,
    perform_update,
    project_removal,
    update_checks,
    update_remotes,
)
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.utils import messages
from weblate.utils.celery import delete_task_metadata
from weblate.utils.files import remove_tree
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED
from weblate.utils.tasks import (
    update_language_stats_parents,
    update_project_stats_link,
    update_translation_stats_parents,
)
from weblate.utils.version import GIT_VERSION


class CleanupTest(ComponentTestCase):
    def test_cleanup_suggestions_case_sensitive(self) -> None:
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, ["Zkouška\n"], request)
        Suggestion.objects.add(unit, ["zkouška\n"], request)
        # This should be ignored
        Suggestion.objects.add(unit, ["zkouška\n"], request)
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Translate string to one of suggestions
        unit.translate(self.user, "zkouška\n", STATE_TRANSLATED)

        # The cleanup should remove one
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_cleanup_suggestions_duplicate(self) -> None:
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, ["Zkouška"], request)
        Suggestion.objects.add(unit, ["zkouška"], request)
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Create two suggestions with same target
        unit.suggestions.update(target="zkouška")

        # The cleanup should remove one
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 1)


class TasksTest(ComponentTestCase):
    def test_repository_commit_uses_locked_wrapper(self) -> None:
        method = Mock()

        with patch("weblate.trans.tasks.perform_component_commit") as commit:
            result = execute_repository_operation_method(
                "commit",
                self.component,
                method,
                self.get_request(),
                self.user,
                ("commit",),
                {},
                resume_followup=None,
                followup_previous_head=None,
            )

        self.assertTrue(result)
        commit.assert_called_once_with(self.component, "commit", self.user)
        method.assert_not_called()

    def test_repository_operation_retry_preserves_resume_state(self) -> None:
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        retry_error = RepositoryOperationRetryError(
            lock_timeout,
            start_index=2,
            successful=False,
            failure_messages=["Earlier repository failure."],
        )

        with (
            patch(
                "weblate.trans.tasks.keep_repository_operation_reservation",
                return_value=nullcontext(),
            ),
            patch("weblate.trans.tasks.acquire_repository_operation"),
            patch(
                "weblate.trans.tasks.store_repository_operation_tracking"
            ) as store_tracking,
            patch(
                "weblate.trans.tasks.execute_repository_operation",
                side_effect=retry_error,
            ),
            patch(
                "weblate.trans.tasks.get_exponential_backoff_interval",
                return_value=600,
            ),
            patch("weblate.trans.tasks.refresh_repository_operation"),
            patch("weblate.trans.tasks.release_repository_operation") as release,
            patch.object(
                perform_repository_operation,
                "retry",
                side_effect=Retry(),
            ) as retry,
            self.assertRaises(Retry),
        ):
            perform_repository_operation.run(
                operation="cleanup",
                component_ids=[1, 2, 3],
                user_id=self.user.pk,
            )

        retry.assert_called_once_with(
            exc=lock_timeout,
            countdown=600,
            kwargs={
                "operation": "cleanup",
                "component_ids": [1, 2, 3],
                "tracking_component_ids": [1, 2, 3],
                "user_id": self.user.pk,
                "start_index": 2,
                "successful": False,
                "failure_messages": ["Earlier repository failure."],
                "resume_followup": None,
                "followup_previous_head": None,
            },
        )
        store_tracking.assert_called_once_with(
            ANY,
            [1, 2, 3],
            self.user.pk,
            authorization_component_ids=[1, 2, 3],
        )
        release.assert_not_called()

    def test_repository_operation_releases_reservation_on_retry_broker_failure(
        self,
    ) -> None:
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        retry_error = RepositoryOperationRetryError(
            lock_timeout, start_index=0, successful=True
        )

        with (
            patch(
                "weblate.trans.tasks.keep_repository_operation_reservation",
                return_value=nullcontext(),
            ),
            patch("weblate.trans.tasks.acquire_repository_operation"),
            patch("weblate.trans.tasks.store_repository_operation_tracking"),
            patch(
                "weblate.trans.tasks.execute_repository_operation",
                side_effect=retry_error,
            ),
            patch("weblate.trans.tasks.refresh_repository_operation"),
            patch("weblate.trans.tasks.release_repository_operation") as release,
            patch.object(
                perform_repository_operation,
                "retry",
                side_effect=RuntimeError("broker failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "broker failure"),
        ):
            perform_repository_operation.run(
                operation="cleanup",
                component_ids=[self.component.pk],
                user_id=self.user.pk,
            )

        release.assert_called_once()

    def test_repository_operation_reports_exhausted_lock_retries(self) -> None:
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        retry_error = RepositoryOperationRetryError(
            lock_timeout, start_index=0, successful=True
        )

        with (
            patch(
                "weblate.trans.tasks.keep_repository_operation_reservation",
                return_value=nullcontext(),
            ),
            patch("weblate.trans.tasks.acquire_repository_operation"),
            patch("weblate.trans.tasks.store_repository_operation_tracking"),
            patch(
                "weblate.trans.tasks.execute_repository_operation",
                side_effect=retry_error,
            ),
            patch.object(perform_repository_operation, "max_retries", 0),
            patch("weblate.trans.tasks.release_repository_operation") as release,
        ):
            result = perform_repository_operation.run(
                operation="cleanup",
                component_ids=[self.component.pk],
                user_id=self.user.pk,
            )

        self.assertFalse(result["result"])
        self.assertEqual(result["completion_message"]["level"], "error")
        self.assertIn("remained locked", result["completion_message"]["text"])
        release.assert_called_once()

    def test_repository_operation_reports_expected_failure(self) -> None:
        with (
            patch(
                "weblate.trans.tasks.keep_repository_operation_reservation",
                return_value=nullcontext(),
            ),
            patch("weblate.trans.tasks.acquire_repository_operation"),
            patch("weblate.trans.tasks.store_repository_operation_tracking"),
            patch(
                "weblate.trans.tasks.execute_repository_operation",
                side_effect=FileParseError(),
            ),
            patch("weblate.trans.tasks.release_repository_operation") as release,
        ):
            result = perform_repository_operation.run(
                operation="file-scan",
                component_ids=[self.component.pk],
                user_id=self.user.pk,
            )

        self.assertFalse(result["result"])
        self.assertEqual(result["completion_message"]["level"], "error")
        self.assertIn("could not be completed", result["completion_message"]["text"])
        release.assert_called_once()

    def test_repository_operation_reports_permission_failure(self) -> None:
        with (
            patch(
                "weblate.trans.tasks.keep_repository_operation_reservation",
                return_value=nullcontext(),
            ),
            patch("weblate.trans.tasks.acquire_repository_operation"),
            patch("weblate.trans.tasks.store_repository_operation_tracking"),
            patch(
                "weblate.trans.tasks.execute_repository_operation",
                side_effect=PermissionDenied,
            ),
            patch("weblate.trans.tasks.release_repository_operation") as release,
        ):
            result = perform_repository_operation.run(
                operation="cleanup",
                component_ids=[self.component.pk],
                user_id=self.user.pk,
            )

        self.assertFalse(result["result"])
        self.assertEqual(result["completion_message"]["level"], "error")
        self.assertIn(
            "access is no longer permitted", result["completion_message"]["text"]
        )
        release.assert_called_once()

    def test_repository_operation_reports_raw_template_failure(self) -> None:
        with (
            patch(
                "weblate.trans.tasks.keep_repository_operation_reservation",
                return_value=nullcontext(),
            ),
            patch("weblate.trans.tasks.acquire_repository_operation"),
            patch("weblate.trans.tasks.store_repository_operation_tracking"),
            patch(
                "weblate.trans.tasks.execute_repository_operation",
                side_effect=ValueError("invalid template"),
            ),
            patch("weblate.trans.tasks.release_repository_operation"),
        ):
            result = perform_repository_operation.run(
                operation="file-scan",
                component_ids=[self.component.pk],
                user_id=self.user.pk,
            )

        self.assertFalse(result["result"])
        self.assertEqual(result["completion_message"]["level"], "error")

    def test_legacy_repository_task_respects_reservation(self) -> None:
        acquire_repository_operation([self.component.pk], "pull", "task-id")
        self.addCleanup(release_repository_operation, [self.component.pk], "task-id")

        with (
            patch.object(Component, "do_update", autospec=True) as update,
            self.assertRaises(RepositoryOperationConflictError),
        ):
            perform_update.run("Component", self.component.pk)

        update.assert_not_called()

    def test_perform_update_publishes_push_after_releasing_reservation(self) -> None:
        events: list[str] = []
        original_push_if_needed = Component.push_if_needed

        @contextmanager
        def reservation(*args, **kwargs):
            events.append("reserve")
            try:
                yield
            finally:
                events.append("release")

        def update(component, request) -> None:
            self.assertIsNotNone(repository_task_deferred_auto_push.get())
            events.append("update")
            original_push_if_needed(component, do_update=False)

        def push(component, *, do_update=True) -> None:
            events.append("push")

        with (
            patch(
                "weblate.trans.tasks.reserve_repository_operation",
                side_effect=reservation,
            ),
            patch.object(Component, "do_update", autospec=True, side_effect=update),
            patch.object(Component, "push_if_needed", autospec=True, side_effect=push),
        ):
            perform_update.run("Component", self.component.pk)

        self.assertEqual(events, ["reserve", "update", "release", "push"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_perform_update_publishes_load_after_releasing_reservation(self) -> None:
        events: list[str] = []
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)

        @contextmanager
        def reservation(*args, **kwargs):
            events.append("reserve")
            try:
                yield
            finally:
                events.append("release")

        def update(component, request) -> None:
            self.assertIsNotNone(repository_task_deferred_background_tasks.get())
            events.append("update")
            component.create_translations()

        def load(*args, **kwargs):
            events.append("load")
            return SimpleNamespace(id="load-task-id")

        with (
            patch(
                "weblate.trans.tasks.reserve_repository_operation",
                side_effect=reservation,
            ),
            patch.object(Component, "do_update", autospec=True, side_effect=update),
            patch.object(
                Component,
                "create_translations_immediate",
                side_effect=lock_timeout,
            ),
            patch(
                "weblate.trans.models.component.current_task",
                SimpleNamespace(request=SimpleNamespace(id="update-task-id")),
            ),
            patch.object(perform_load, "delay", side_effect=load),
            patch(
                "weblate.trans.models.component.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ),
        ):
            perform_update.run("Component", self.component.pk)

        self.assertEqual(events, ["reserve", "update", "release", "load"])

    def test_perform_update_persistently_retries_reservation_conflict(self) -> None:
        conflict = RepositoryOperationConflictError("repository-task-id")
        perform_update.push_request(retries=10, kwargs={})
        try:
            with (
                patch(
                    "weblate.trans.tasks.reserve_repository_operation",
                    side_effect=conflict,
                ),
                patch(
                    "weblate.trans.tasks.get_exponential_backoff_interval",
                    return_value=3600,
                ),
                patch.object(perform_update, "retry", side_effect=Retry()) as retry,
                self.assertRaises(Retry),
            ):
                perform_update.run("Component", self.component.pk)
        finally:
            perform_update.pop_request()

        retry.assert_called_once_with(exc=conflict, countdown=3600, kwargs={})

    def test_perform_update_preserves_lock_retry_budget_after_conflicts(self) -> None:
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        perform_update.push_request(retries=10, kwargs={})
        try:
            with (
                patch.object(Component, "do_update", side_effect=lock_timeout),
                patch(
                    "weblate.trans.tasks.get_exponential_backoff_interval",
                    return_value=600,
                ),
                patch.object(perform_update, "retry", side_effect=Retry()) as retry,
                self.assertRaises(Retry),
            ):
                perform_update.run(
                    "Component",
                    self.component.pk,
                    _repository_lock_retries=1,
                )
        finally:
            perform_update.pop_request()

        retry.assert_called_once_with(
            exc=lock_timeout,
            countdown=600,
            kwargs={"_repository_lock_retries": 2},
        )

    def test_perform_update_exhausts_only_lock_retry_budget(self) -> None:
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        perform_update.push_request(retries=10, kwargs={})
        try:
            with (
                patch.object(Component, "do_update", side_effect=lock_timeout),
                patch.object(perform_update, "retry") as retry,
                self.assertRaises(WeblateLockTimeoutError),
            ):
                perform_update.run(
                    "Component",
                    self.component.pk,
                    _repository_lock_retries=3,
                )
        finally:
            perform_update.pop_request()

        retry.assert_not_called()

    def test_perform_load_persistently_retries_reservation_conflict(self) -> None:
        conflict = RepositoryOperationConflictError("repository-task-id")
        perform_load.push_request(retries=10, kwargs={})
        try:
            with (
                patch(
                    "weblate.trans.tasks.reserve_repository_operation",
                    side_effect=conflict,
                ),
                patch(
                    "weblate.trans.tasks.get_exponential_backoff_interval",
                    return_value=3600,
                ),
                patch.object(perform_load, "retry", side_effect=Retry()) as retry,
                self.assertRaises(Retry),
            ):
                perform_load.run(self.component.pk)
        finally:
            perform_load.pop_request()

        retry.assert_called_once_with(exc=conflict, countdown=3600, kwargs={})

    def test_perform_push_persistently_retries_reservation_conflict(self) -> None:
        conflict = RepositoryOperationConflictError("repository-task-id")
        perform_push.push_request(retries=10, kwargs={})
        try:
            with (
                patch(
                    "weblate.trans.tasks.reserve_repository_operation",
                    side_effect=conflict,
                ),
                patch(
                    "weblate.trans.tasks.get_exponential_backoff_interval",
                    return_value=3600,
                ),
                patch.object(perform_push, "retry", side_effect=Retry()) as retry,
                self.assertRaises(Retry),
            ):
                perform_push.run(self.component.pk)
        finally:
            perform_push.pop_request()

        retry.assert_called_once_with(exc=conflict, countdown=3600, kwargs={})

    def test_repository_operation_revalidates_permission(self) -> None:
        task = SimpleNamespace(update_state=Mock())
        with (
            patch.object(User, "has_perm", return_value=False),
            patch.object(Component, "do_cleanup", autospec=True) as cleanup,
            self.assertRaises(PermissionDenied),
        ):
            execute_repository_operation(
                task,
                "cleanup",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        cleanup.assert_not_called()

    def test_repository_operation_rejects_changed_repository_link(self) -> None:
        repository = self.create_po(project=self.project, name="Other repository")
        Component.objects.filter(pk=self.component.pk).update(
            repo=repository.get_repo_link_url(), linked_component=repository
        )
        task = SimpleNamespace(update_state=Mock())

        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_cleanup", autospec=True) as cleanup,
        ):
            result = execute_repository_operation(
                task,
                "cleanup",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        self.assertFalse(result["result"])
        cleanup.assert_not_called()

    def test_repository_operation_preserves_failure_message(self) -> None:
        task = SimpleNamespace(update_state=Mock())

        def cleanup(component, request):
            messages.error(request, "Specific repository failure.")
            return False

        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_cleanup", autospec=True, side_effect=cleanup),
        ):
            result = execute_repository_operation(
                task,
                "cleanup",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        self.assertFalse(result["result"])
        self.assertEqual(
            result["completion_message"],
            {"level": "error", "text": "Specific repository failure."},
        )

    def test_repository_operation_retries_only_file_sync_commit(self) -> None:
        task = SimpleNamespace(update_state=Mock())
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        followup_error = RepositoryFollowupLockError(lock_timeout, "file-sync")

        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(
                Component,
                "do_file_sync",
                autospec=True,
                side_effect=followup_error,
            ),
            self.assertRaises(RepositoryOperationRetryError) as raised,
        ):
            execute_repository_operation(
                task,
                "file-sync",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        self.assertEqual(raised.exception.resume_followup, "file-sync")
        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_file_sync", autospec=True) as file_sync,
            patch("weblate.trans.tasks.perform_component_commit") as commit,
        ):
            result = execute_repository_operation(
                task,
                "file-sync",
                [self.component.pk],
                self.user.pk,
                "task-id",
                start_index=raised.exception.start_index,
                successful=raised.exception.successful,
                resume_followup=raised.exception.resume_followup,
                followup_previous_head=raised.exception.followup_previous_head,
            )

        self.assertTrue(result["result"])
        file_sync.assert_not_called()
        commit.assert_called_once_with(self.component, "file-sync", self.user)

    def test_repository_operation_retries_only_pull_followup(self) -> None:
        task = perform_repository_operation
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        followup_error = RepositoryFollowupLockError(lock_timeout, "pull")

        with (
            patch.object(task, "update_state"),
            patch.object(User, "has_perm", return_value=True),
            patch.object(
                Component,
                "do_update",
                autospec=True,
                side_effect=followup_error,
            ),
            self.assertRaises(RepositoryOperationRetryError) as raised,
        ):
            execute_repository_operation(
                task,
                "pull",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        self.assertEqual(raised.exception.resume_followup, "pull")
        with (
            patch.object(task, "update_state"),
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_update", autospec=True) as update,
            patch.object(Component, "finish_update", autospec=True) as finish_update,
        ):
            result = execute_repository_operation(
                task,
                "pull",
                [self.component.pk],
                self.user.pk,
                "task-id",
                start_index=raised.exception.start_index,
                successful=raised.exception.successful,
                resume_followup=raised.exception.resume_followup,
                followup_previous_head=raised.exception.followup_previous_head,
            )

        self.assertTrue(result["result"])
        update.assert_not_called()
        finish_update.assert_called_once_with(self.component, ANY, self.user)

    def test_repository_operation_resumes_push_after_pull_followup(self) -> None:
        task = perform_repository_operation
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        followup_error = RepositoryFollowupLockError(lock_timeout, "pull")

        with (
            patch.object(task, "update_state"),
            patch.object(User, "has_perm", return_value=True),
            patch.object(
                Component,
                "do_push",
                autospec=True,
                side_effect=followup_error,
            ),
            self.assertRaises(RepositoryOperationRetryError) as raised,
        ):
            execute_repository_operation(
                task,
                "push",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        with (
            patch.object(task, "update_state"),
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "finish_update", autospec=True) as finish_update,
            patch.object(
                Component, "do_push", autospec=True, return_value=True
            ) as push,
        ):
            result = execute_repository_operation(
                task,
                "push",
                [self.component.pk],
                self.user.pk,
                "task-id",
                start_index=raised.exception.start_index,
                successful=raised.exception.successful,
                resume_followup=raised.exception.resume_followup,
                followup_previous_head=raised.exception.followup_previous_head,
            )

        self.assertTrue(result["result"])
        finish_update.assert_called_once_with(self.component, ANY, self.user)
        push.assert_called_once_with(
            self.component, ANY, force_commit=False, do_update=False
        )

    def test_repository_operation_retries_only_reset_followup(self) -> None:
        task = SimpleNamespace(update_state=Mock())
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        followup_error = RepositoryFollowupLockError(
            lock_timeout, "reset-keep", previous_head="previous-head"
        )

        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(
                Component,
                "do_reset",
                autospec=True,
                side_effect=followup_error,
            ),
            self.assertRaises(RepositoryOperationRetryError) as raised,
        ):
            execute_repository_operation(
                task,
                "reset-keep",
                [self.component.pk],
                self.user.pk,
                "task-id",
            )

        self.assertEqual(raised.exception.resume_followup, "reset-keep")
        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_reset", autospec=True) as reset,
            patch("weblate.trans.tasks.perform_component_commit") as commit,
        ):
            result = execute_repository_operation(
                task,
                "reset-keep",
                [self.component.pk],
                self.user.pk,
                "task-id",
                start_index=raised.exception.start_index,
                successful=raised.exception.successful,
                resume_followup=raised.exception.resume_followup,
                followup_previous_head=raised.exception.followup_previous_head,
            )

        self.assertTrue(result["result"])
        reset.assert_not_called()
        commit.assert_called_once_with(
            self.component,
            "reset-sync",
            self.user,
            force_scan=True,
            previous_head="previous-head",
        )

    def test_repository_operation_retry_resumes_timed_out_repository(self) -> None:
        second = self.create_po(project=self.project, name="Second")
        self.addCleanup(delete_task_metadata, "task-id")
        task = SimpleNamespace(update_state=Mock())
        calls: list[int] = []
        lock_timeout = WeblateLockTimeoutError("locked", lock=second.lock)

        def cleanup(component, request):
            calls.append(component.pk)
            if component == self.component:
                messages.error(request, "Earlier repository failure.")
                return False
            if component == second and calls.count(second.pk) == 1:
                raise lock_timeout
            return True

        component_ids = [self.component.pk, second.pk]
        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_cleanup", autospec=True, side_effect=cleanup),
            patch("weblate.trans.tasks.refresh_repository_operation"),
            self.assertRaises(RepositoryOperationRetryError) as raised,
        ):
            execute_repository_operation(
                task, "cleanup", component_ids, self.user.pk, "task-id"
            )

        self.assertEqual(raised.exception.start_index, 1)
        self.assertEqual(
            raised.exception.failure_messages, ["Earlier repository failure."]
        )

        with (
            patch.object(User, "has_perm", return_value=True),
            patch.object(Component, "do_cleanup", autospec=True, side_effect=cleanup),
            patch("weblate.trans.tasks.refresh_repository_operation"),
        ):
            result = execute_repository_operation(
                task,
                "cleanup",
                component_ids,
                self.user.pk,
                "task-id",
                start_index=raised.exception.start_index,
                successful=raised.exception.successful,
                failure_messages=raised.exception.failure_messages,
            )

        self.assertFalse(result["result"])
        self.assertEqual(
            result["completion_message"]["text"], "Earlier repository failure."
        )
        self.assertEqual(calls, [self.component.pk, second.pk, second.pk])

    def test_project_removal_retries_without_backup(self) -> None:
        task_id = "project-removal-task-id"
        original_get = Project.objects.get
        attempts = 0

        def get_project(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise IntegrityError
            return original_get(*args, **kwargs)

        with (
            patch("weblate.trans.tasks.create_project_backup") as create_project_backup,
            patch(
                "weblate.trans.tasks.get_exponential_backoff_interval", return_value=0
            ) as get_backoff,
            patch.object(Project.objects, "get", side_effect=get_project),
        ):
            result = project_removal.apply(
                args=(self.project.pk, self.user.pk), task_id=task_id, throw=False
            )

        self.assertTrue(result.successful())
        self.assertEqual(result.id, task_id)
        self.assertEqual(attempts, 2)
        create_project_backup.assert_called_once_with(self.project.pk)
        get_backoff.assert_called_once_with(
            factor=600, retries=0, maximum=3600, full_jitter=True
        )
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_component_alerts_processes_canonical_component_first(self) -> None:
        second = self.create_po(project=self.project, name="Second")
        processed: list[int] = []

        with patch.object(
            Component,
            "update_alerts",
            autospec=True,
            side_effect=lambda component: processed.append(component.pk),
        ):
            component_alerts([second.pk, self.component.pk])

        self.assertEqual(processed, [self.component.pk, second.pk])

    def test_daily_update_checks(self) -> None:
        daily_update_checks()

    def test_update_checks_uses_narrow_prefetches(self) -> None:
        category = Category.objects.create(
            project=self.project, name="WorkshopApp", slug="workshopapp"
        )
        self.component.category = category
        self.component.save(update_fields=["category"])

        with (
            patch.object(Component, "run_batched_checks", autospec=True) as batched,
            CaptureQueriesContext(connection) as queries,
        ):
            update_checks(self.component.pk, "update-token")

        batched.assert_called_once()
        sql_queries = [query["sql"] for query in queries]

        def count_relation_prefetches(table: str) -> int:
            marker = f'FROM "{table}" WHERE ("{table}"."id") IN'
            return sum(marker in sql for sql in sql_queries)

        self.assertLessEqual(count_relation_prefetches("trans_project"), 1)
        self.assertLessEqual(count_relation_prefetches("trans_category"), 1)
        self.assertLessEqual(count_relation_prefetches("trans_component"), 1)

    def test_cleanup_repos(self) -> None:
        cleanup_repos()

    def test_cleanup_stale_repos_keeps_category_with_stale_git_dir(self) -> None:
        category = Category.objects.create(
            project=self.project, name="WorkshopApp", slug="workshopapp"
        )
        component = self.create_po(
            project=self.project, category=category, name="startup", vcs="local"
        )
        stale_git = Path(category.full_path) / ".git"
        stale_git.mkdir()
        (stale_git / "config").write_text("[core]\n", encoding="utf-8")

        old_timestamp = time.time() - 2 * 86400
        os.utime(category.full_path, (old_timestamp, old_timestamp))
        os.utime(component.full_path, (old_timestamp, old_timestamp))

        cleanup_stale_repos()

        self.assertTrue(os.path.isdir(category.full_path))
        self.assertTrue(os.path.isdir(component.full_path))
        self.assertTrue(
            os.path.isfile(os.path.join(component.full_path, ".git", "config"))
        )

    def test_cleanup_stale_repos_keeps_empty_component_dir(self) -> None:
        component = self.create_po(project=self.project, name="empty", vcs="local")
        component_path = Path(component.full_path)

        for entry in component_path.iterdir():
            if entry.is_dir():
                remove_tree(entry)
            else:
                entry.unlink()

        old_timestamp = time.time() - 2 * 86400
        os.utime(component_path, (old_timestamp, old_timestamp))

        cleanup_stale_repos()

        self.assertTrue(component_path.is_dir())

    def test_update_remotes(self) -> None:
        current_time = timezone.now().replace(hour=self.component.pk % 24)
        with (
            patch("weblate.trans.tasks.timezone.now", return_value=current_time),
            patch.object(perform_update, "delay") as update,
        ):
            update_remotes()

        update.assert_any_call("Component", self.component.pk, auto=True)

    def test_commit_pending(self) -> None:
        self.component.commit_pending_age = 1
        self.component.save()

        component2 = self.create_ftl(name="Component 2", project=self.project)
        component2.commit_pending_age = 3
        component2.save()

        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Nazdar svete!\n", STATE_TRANSLATED)

        translation2 = component2.translation_set.get(language_code="cs")
        unit2 = translation2.unit_set.get(source="Hello, ${ name }!")
        unit2.translate(self.user, "Ahoj ${ name }!\n", STATE_TRANSLATED)

        self.assertEqual(self.component.count_pending_units, 1)
        self.assertEqual(component2.count_pending_units, 1)

        PendingUnitChange.objects.update(timestamp=timezone.now() - timedelta(hours=2))

        commit_pending()
        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 1)

        commit_pending(hours=1)
        self.assertEqual(component2.count_pending_units, 0)

    def test_perform_commit_keeps_commit_task_on_pending_lock_retry(self) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        task = SimpleNamespace(
            request=SimpleNamespace(id="commit-task-id", retries=2), max_retries=3
        )

        with (
            patch("weblate.trans.models.component.current_task", task),
            patch("weblate.trans.tasks.current_task", task),
            patch.object(Component, "commit_pending", side_effect=lock_timeout),
            self.assertRaises(WeblateLockTimeoutError),
        ):
            perform_commit.run(self.component.pk, "commit")

        self.assertEqual(cache.get(self.component.commit_task_key), "commit-task-id")
        cache.delete(self.component.commit_task_key)

    def test_perform_commit_publishes_push_after_releasing_reservation(self) -> None:
        events: list[str] = []

        @contextmanager
        def reservation(*args, **kwargs):
            events.append("reserve")
            try:
                yield
            finally:
                events.append("release")

        def commit(*args, **kwargs) -> None:
            self.assertTrue(repository_task_suppress_auto_push.get())
            events.append("commit")

        def push(*args, **kwargs) -> None:
            events.append("push")

        with (
            patch(
                "weblate.trans.tasks.reserve_repository_operation",
                side_effect=reservation,
            ),
            patch("weblate.trans.tasks.perform_component_commit", side_effect=commit),
            patch.object(Component, "push_if_needed", autospec=True, side_effect=push),
            patch("weblate.trans.tasks.schedule_deferred_commit") as schedule,
        ):
            perform_commit.run(self.component.pk, "commit")

        self.assertEqual(events, ["reserve", "commit", "release", "push"])
        schedule.assert_called_once()

    def test_perform_commit_clears_commit_task_on_exhausted_lock_retry(self) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        task = SimpleNamespace(
            request=SimpleNamespace(id="commit-task-id", retries=3), max_retries=3
        )

        with (
            patch("weblate.trans.models.component.current_task", task),
            patch("weblate.trans.tasks.current_task", task),
            patch.object(Component, "commit_pending", side_effect=lock_timeout),
            self.assertRaises(WeblateLockTimeoutError),
        ):
            perform_commit.run(self.component.pk, "commit")

        self.assertIsNone(cache.get(self.component.commit_task_key))

    def test_perform_commit_clears_commit_task_on_exhausted_reservation_retry(
        self,
    ) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        task = SimpleNamespace(
            request=SimpleNamespace(id="commit-task-id", retries=3), max_retries=3
        )

        with (
            patch("weblate.trans.models.component.current_task", task),
            patch("weblate.trans.tasks.current_task", task),
            patch(
                "weblate.trans.tasks.reserve_repository_operation",
                side_effect=RepositoryOperationConflictError("repository-task-id"),
            ),
            self.assertRaises(RepositoryOperationConflictError),
        ):
            perform_commit.run(self.component.pk, "commit")

        self.assertIsNone(cache.get(self.component.commit_task_key))

    def test_perform_commit_keeps_other_commit_task_on_exhausted_lock_retry(
        self,
    ) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        task = SimpleNamespace(
            request=SimpleNamespace(id="background-task-id", retries=3), max_retries=3
        )

        with (
            patch("weblate.trans.models.component.current_task", task),
            patch("weblate.trans.tasks.current_task", task),
            patch.object(Component, "commit_pending", side_effect=lock_timeout),
            self.assertRaises(WeblateLockTimeoutError),
        ):
            perform_commit.run(self.component.pk, "commit")

        self.assertEqual(cache.get(self.component.commit_task_key), "commit-task-id")
        cache.delete(self.component.commit_task_key)

    def test_perform_commit_schedules_deferred_commit_on_exhausted_lock_retry(
        self,
    ) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        cache.set(
            self.component.commit_task_reschedule_key,
            {
                "reason": "commit",
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
        )
        lock_timeout = WeblateLockTimeoutError("locked", lock=self.component.lock)
        task = SimpleNamespace(
            request=SimpleNamespace(id="commit-task-id", retries=3), max_retries=3
        )

        with (
            override_settings(CELERY_TASK_ALWAYS_EAGER=False),
            patch("weblate.trans.models.component.current_task", task),
            patch("weblate.trans.tasks.current_task", task),
            patch.object(Component, "commit_pending", side_effect=lock_timeout),
            patch("weblate.trans.models.component.uuid", return_value="next-task-id"),
            patch.object(perform_commit, "apply_async") as apply_async,
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(WeblateLockTimeoutError),
        ):
            perform_commit.run(self.component.pk, "commit")

        apply_async.assert_called_once_with(
            args=(self.component.pk, "commit"),
            kwargs={
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
            task_id="next-task-id",
        )
        self.assertEqual(cache.get(self.component.commit_task_key), "next-task-id")
        self.assertIsNone(cache.get(self.component.commit_task_reschedule_key))
        self.component.delete_commit_task()

    def test_perform_commit_schedules_deferred_commit_request(self) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        cache.set(
            self.component.commit_task_reschedule_key,
            {
                "reason": "commit",
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
        )

        with (
            override_settings(CELERY_TASK_ALWAYS_EAGER=False),
            patch(
                "weblate.trans.models.component.current_task",
                SimpleNamespace(request=SimpleNamespace(id="commit-task-id")),
            ),
            patch(
                "weblate.trans.tasks.current_task",
                SimpleNamespace(request=SimpleNamespace(id="commit-task-id")),
            ),
            patch.object(Component, "commit_pending", return_value=True),
            patch("weblate.trans.models.component.uuid", return_value="next-task-id"),
            patch.object(perform_commit, "apply_async") as apply_async,
            self.captureOnCommitCallbacks(execute=True),
        ):
            perform_commit.run(self.component.pk, "commit_pending")

        apply_async.assert_called_once_with(
            args=(self.component.pk, "commit"),
            kwargs={
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
            task_id="next-task-id",
        )
        self.assertEqual(cache.get(self.component.commit_task_key), "next-task-id")
        self.assertIsNone(cache.get(self.component.commit_task_reschedule_key))
        self.component.delete_commit_task()

    def test_perform_commit_keeps_other_commit_task_on_success(self) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        cache.set(
            self.component.commit_task_reschedule_key,
            {
                "reason": "commit",
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
        )

        with (
            override_settings(CELERY_TASK_ALWAYS_EAGER=False),
            patch(
                "weblate.trans.models.component.current_task",
                SimpleNamespace(request=SimpleNamespace(id="background-task-id")),
            ),
            patch(
                "weblate.trans.tasks.current_task",
                SimpleNamespace(request=SimpleNamespace(id="background-task-id")),
            ),
            patch.object(Component, "commit_pending", return_value=True),
            patch.object(perform_commit, "apply_async") as apply_async,
        ):
            perform_commit.run(self.component.pk, "commit")

        apply_async.assert_not_called()
        self.assertEqual(cache.get(self.component.commit_task_key), "commit-task-id")
        self.assertEqual(
            cache.get(self.component.commit_task_reschedule_key),
            {
                "reason": "commit",
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
        )
        self.component.delete_commit_task()

    def test_perform_commit_clears_commit_task_on_missing_user(self) -> None:
        cache.set(self.component.commit_task_key, "commit-task-id")
        cache.set(
            self.component.commit_task_reschedule_key,
            {
                "reason": "commit",
                "user_id": self.user.id,
                "force_scan": False,
                "previous_head": None,
            },
        )
        task = SimpleNamespace(request=SimpleNamespace(id="commit-task-id"))

        with (
            patch("weblate.trans.models.component.current_task", task),
            patch("weblate.trans.tasks.current_task", task),
            patch.object(Component, "commit_pending") as commit_pending_mock,
            self.assertRaises(User.DoesNotExist),
        ):
            perform_commit.run(self.component.pk, "commit", user_id=-1)

        commit_pending_mock.assert_not_called()
        self.assertIsNone(cache.get(self.component.commit_task_key))
        self.assertIsNone(cache.get(self.component.commit_task_reschedule_key))

    @patch("weblate.trans.tasks.perform_commit")
    def test_commit_pending_with_ineligible_changes(self, mock_perform_commit) -> None:
        """Test that perform_commit is not called when all changes are ineligible."""
        mock_perform_commit.delay.return_value.id = "commit-task-id"
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.save()

        self.component.commit_pending_age = 1
        self.component.save()

        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Nazdar svete!\n", STATE_FUZZY)

        component2 = self.create_ftl(name="Component 2", project=self.project)
        component2.commit_pending_age = 1
        component2.save()

        translation2 = component2.translation_set.get(language_code="cs")
        unit2 = translation2.unit_set.get(source="Hello, ${ name }!")
        unit2.translate(self.user, "Ahoj ${ name }!\n", STATE_TRANSLATED)

        pending_change = unit2.pending_changes.first()
        pending_change.metadata = {
            "last_failed": timezone.now().isoformat(),
            "failed_revision": translation2.revision,
            "weblate_version": GIT_VERSION,
            "blocking_unit": True,
        }
        pending_change.save()

        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            1,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

        PendingUnitChange.objects.update(timestamp=timezone.now() - timedelta(hours=2))

        commit_pending()
        mock_perform_commit.delay.assert_not_called()

        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            1,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

        unit.translate(self.user, "Nazdar svete!\n", STATE_TRANSLATED)
        PendingUnitChange.objects.update(timestamp=timezone.now() - timedelta(hours=2))

        self.assertEqual(self.component.count_pending_units, 1)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            2,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

        commit_pending()
        mock_perform_commit.delay.assert_called_with(
            self.component.pk,
            "commit_pending",
            user_id=None,
            force_scan=False,
            previous_head=None,
        )

        # actually call commit_pending on the component to test count_pending_units is updated
        self.component.commit_pending("commit_pending", None)
        component2.commit_pending("commit_pending", None)

        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            0,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

    def test_update_translation_stats_parents_missing_translation(self) -> None:
        update_translation_stats_parents(-1)

    def test_update_language_stats_parents_missing_component(self) -> None:
        update_language_stats_parents(-1)

    def test_update_project_stats_link_missing_project(self) -> None:
        update_project_stats_link(-1)

    def test_finalize_component_checks_missing_component(self) -> None:
        finalize_component_checks(-1, [], ["same"], batch_mode=True)

    def test_finalize_component_checks_missing_source_translation(self) -> None:
        source_translation = self.component.get_source_translation()
        self.assertIsNotNone(source_translation)
        source_translation.delete()
        self.component.__dict__.pop("source_translation", None)

        finalize_component_checks(
            self.component.id, [], ["multiple_failures"], batch_mode=True
        )

        self.assertFalse(
            self.component.translation_set.filter(
                language=self.component.source_language
            ).exists()
        )
