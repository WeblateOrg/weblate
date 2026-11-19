# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch
from uuid import uuid4

from celery.exceptions import Retry
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse

from weblate.checks.models import Check
from weblate.machinery.base import MachineTranslationError
from weblate.trans.automation import automatic_translation
from weblate.trans.autotranslate import (
    AutoTranslate,
    BaseAutoTranslate,
    BatchAutoTranslate,
)
from weblate.trans.component_copy import auto_translate_component_copy
from weblate.trans.coordination import (
    AutomaticTranslationBusyError,
    TranslationContinuation,
    ensure_translation_session,
    translation_continuation,
    translation_guard,
    translation_task,
)
from weblate.trans.models import Component, Translation
from weblate.trans.tasks import auto_translate, auto_translate_component
from weblate.trans.tests.test_views import ReusableViewTestCase
from weblate.utils.celery import app, get_task_progress, sanitize_task_result
from weblate.utils.change_origin import ACTING_USER_HEADER, CHANGE_ORIGIN_HEADER
from weblate.utils.lock import WeblateLockTimeoutError

if TYPE_CHECKING:
    from collections.abc import Generator


@contextmanager
def competing_translation(translation_id: int) -> Generator[None]:
    ready, release = Event(), Event()

    def hold() -> None:
        close_old_connections()
        try:
            with translation_guard(translation_id):
                ready.set()
                if not release.wait(30):
                    msg = "Test did not release translation guard"
                    raise TimeoutError(msg)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold)
        try:
            if not ready.wait(10):
                msg = "Test did not acquire translation guard"
                raise TimeoutError(msg)
            yield
        finally:
            release.set()
            future.result(timeout=10)


class TranslationCoordinationIntegrationTest(ReusableViewTestCase):
    def test_partial_component_batch_flushes_checks_before_deferral(self) -> None:
        completed = self.translation
        busy = self.component.translation_set.get(language_code="de")
        unit = completed.unit_set.get(source="Hello, world!\n")
        # Removing this obsolete warning also requires refreshing source checks.
        Check.objects.get_or_create(unit=unit, name="python_format")
        state = TranslationContinuation(
            {"targets": [completed.pk, busy.pk]}, defer=True
        )
        token = translation_continuation.set(state)
        configuration = {
            "mode": "translate",
            "q": "",
            "auto_source": "mt",
            "engines": [],
            "threshold": 80,
            "component": None,
        }
        try:
            with (
                self.settings(CELERY_TASK_ALWAYS_EAGER=False),
                patch(
                    "weblate.trans.autotranslate.fetch_machinery_matches",
                    return_value={
                        unit.pk: {
                            "translation": ["Completed language\n"],
                            "quality": [100],
                            "origin": [None],
                        }
                    },
                ) as fetch,
                patch(
                    "weblate.checks.tasks.finalize_component_checks.delay_on_commit"
                ) as finalize,
            ):
                with (
                    competing_translation(busy.pk),
                    self.assertRaises(AutomaticTranslationBusyError),
                ):
                    automatic_translation(
                        self.component,
                        configuration,
                        self.user,
                        enforce_permissions=False,
                    )
                unit.refresh_from_db()
                self.assertEqual(unit.target, "Completed language\n")
                self.assertEqual(state.completed, {completed.pk})
                finalize.assert_called_once()
                self.assertEqual(finalize.call_args.args[0], self.component.pk)
                self.assertIn(unit.source_unit_id, finalize.call_args.args[1])
                self.assertEqual(self.component.updated_sources, set())

                fetch.reset_mock()
                fetch.return_value = {}
                result = automatic_translation(
                    Component.objects.get(pk=self.component.pk),
                    configuration,
                    self.user,
                    enforce_permissions=False,
                )
                self.assertEqual(result["updated"], 1)
                fetch.assert_called_once()
                self.assertTrue(
                    all(
                        candidate.translation_id == busy.pk
                        for candidate in fetch.call_args.kwargs["units"]
                    )
                )
        finally:
            translation_continuation.reset(token)

    def test_busy_component_copy_reports_failure(self) -> None:
        with (
            competing_translation(self.translation.pk),
            self.assertRaisesMessage(MachineTranslationError, "already running"),
        ):
            auto_translate_component_copy(self.component, self.component)

    def test_busy_translation_does_not_fetch_provider_results(self) -> None:
        auto = AutoTranslate(
            user=self.user, translation=self.translation, q="", mode="translate"
        )
        with (
            competing_translation(self.translation.pk),
            patch.object(auto, "fetch_mt") as fetch,
        ):
            auto.perform(
                auto_source="mt", engines=[], threshold=80, source_component_ids=None
            )
        fetch.assert_not_called()
        self.assertTrue(auto.busy)
        self.assertIn("already running", auto.failure_message or "")

    def test_busy_command_reports_failure(self) -> None:
        with (
            competing_translation(self.translation.pk),
            self.assertRaisesMessage(CommandError, "already running"),
        ):
            call_command(
                "auto_translate",
                self.project.slug,
                self.component.slug,
                self.translation.language.code,
                user=self.user.username,
            )

    def test_busy_synchronous_api_preserves_error_response(self) -> None:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.client.force_login(self.user)
        url = reverse(
            "api:translation-autotranslate",
            kwargs={
                "component__project__slug": self.project.slug,
                "component__slug": self.component.slug,
                "language__code": self.translation.language.code,
            },
        )
        with competing_translation(self.translation.pk):
            response = self.client.post(
                url,
                {
                    "mode": "translate",
                    "q": "state:<translated",
                    "auto_source": "others",
                    "threshold": 80,
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("already running", response.json()["errors"][0])

    def test_busy_celery_task_retries_with_original_identity_and_headers(self) -> None:
        task_id = str(uuid4())
        headers = {
            ACTING_USER_HEADER: self.user.pk,
            CHANGE_ORIGIN_HEADER: {"scope": "repository"},
        }
        for task in (auto_translate, auto_translate_component):
            kwargs = {
                "user_id": self.user.pk,
                "mode": "translate",
                "q": "",
                "auto_source": "mt",
                "source_component_id": None,
                "engines": [],
                "threshold": 80,
                "enforce_permissions": False,
            }
            if task is auto_translate:
                kwargs["translation_id"] = self.translation.pk
            else:
                kwargs["component_id"] = self.component.pk
            task.push_request(
                id=task_id,
                args=(),
                kwargs=kwargs,
                headers=headers,
                called_directly=False,
                is_eager=False,
                delivery_info={},
            )
            try:
                with (
                    competing_translation(self.translation.pk),
                    patch("weblate.trans.coordination.current_task", task),
                    patch.object(task, "apply_async") as publish,
                    patch(
                        "weblate.trans.tasks.store_auto_translate_activity_log"
                    ) as store,
                    self.assertRaises(Retry),
                ):
                    task.run(
                        **kwargs, _translation_resume={"targets": [self.translation.pk]}
                    )
                options = publish.call_args.kwargs
                self.assertEqual(options["task_id"], task_id)
                self.assertEqual(options["headers"], headers)
                self.assertIn(
                    self.translation.pk,
                    publish.call_args.args[1]["_translation_resume"]["targets"],
                )
                store.assert_not_called()
            finally:
                task.pop_request()


class TranslationGuardTest(TransactionTestCase):
    def contender(self, identifier: int, *, busy: bool) -> None:
        close_old_connections()
        try:
            if busy:
                with (
                    self.assertRaises(AutomaticTranslationBusyError),
                    translation_guard(identifier),
                ):
                    self.fail("Competing translation acquired the guard")
            else:
                with translation_guard(identifier):
                    ensure_translation_session()
        finally:
            connection.close()

    def check_contender(self, identifier: int, *, busy: bool) -> None:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(self.contender, identifier, busy=busy).result(timeout=10)

    def test_same_translation_exclusive_and_different_translation_parallel(
        self,
    ) -> None:
        with translation_guard(1):
            self.check_contender(1, busy=True)
            self.check_contender(2, busy=False)
        self.check_contender(1, busy=False)

    def test_guard_survives_transaction_commit(self) -> None:
        with translation_guard(1):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            self.check_contender(1, busy=True)

    def test_enclosing_transaction_retains_guard_until_commit(self) -> None:
        with transaction.atomic():
            with translation_guard(1):
                pass
            self.check_contender(1, busy=True)
        self.check_contender(1, busy=False)

    def test_enclosing_transaction_rollback_releases_guard(self) -> None:
        with self.assertRaises(ValueError), transaction.atomic():
            with translation_guard(1):
                pass
            self.check_contender(1, busy=True)
            raise ValueError
        self.check_contender(1, busy=False)

    def test_provider_error_releases_guard(self) -> None:
        with self.assertRaises(ValueError), translation_guard(1):
            raise ValueError
        self.check_contender(1, busy=False)

    def test_broken_transaction_does_not_leak_session_guard(self) -> None:
        with (
            self.assertRaises(DatabaseError),
            transaction.atomic(),
            translation_guard(1),
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1 / 0")
        self.check_contender(1, busy=False)

    def test_session_loss_releases_guard_and_rejects_results(self) -> None:
        with self.assertRaises(AutomaticTranslationBusyError), translation_guard(1):
            connection.close()
            self.check_contender(1, busy=False)
            ensure_translation_session()

    def test_closed_backend_does_not_mask_session_loss_during_unlock(self) -> None:
        with self.assertRaises(AutomaticTranslationBusyError), translation_guard(1):
            connection.connection.close()
            ensure_translation_session()
        self.check_contender(1, busy=False)


class TranslationContinuationTest(SimpleTestCase):
    def test_retry_backend_retains_progress_and_reports_waiting(self) -> None:
        error = AutomaticTranslationBusyError(1, 50)
        restored = app.backend.exception_to_python(app.backend.prepare_exception(error))
        self.assertIsInstance(restored, AutomaticTranslationBusyError)
        task = SimpleNamespace(state="RETRY", result=restored, ready=lambda: False)
        self.assertEqual(get_task_progress(task), 50)
        self.assertEqual(
            sanitize_task_result("task-id", restored, Mock()),
            "Automatic translation is waiting for another operation to finish.",
        )

    def make_batch(self) -> BatchAutoTranslate:
        batch = BatchAutoTranslate.__new__(BatchAutoTranslate)
        BaseAutoTranslate.__init__(batch, user=None, q="", mode="translate")
        batch.translations = [Translation(pk=1), Translation(pk=2)]
        batch.workspace_source_component_ids = None
        batch._task_meta = {}  # ruff: ignore[private-member-access]
        batch.enforce_permissions = False
        self.enterContext(patch.object(batch, "set_progress", Mock()))
        return batch

    def translation(self, *, busy: bool = False) -> SimpleNamespace:
        return SimpleNamespace(
            perform=Mock(
                side_effect=AutomaticTranslationBusyError(1) if busy else None
            ),
            updated=2,
            busy=False,
            failure_message=None,
            affected_unit_ids=set(),
            affected_source_unit_ids=set(),
            get_errors=list,
            get_error_details=list,
            get_warning_details=list,
        )

    def test_busy_target_resumes_without_repeating_completed_target(self) -> None:
        state = TranslationContinuation({}, defer=True)
        token = translation_continuation.set(state)
        first, second = self.translation(busy=True), self.translation()
        try:
            batch = self.make_batch()
            with (
                patch(
                    "weblate.trans.autotranslate.AutoTranslate",
                    side_effect=[first, second],
                ),
                self.assertRaises(AutomaticTranslationBusyError),
            ):
                batch.perform(
                    auto_source="mt",
                    engines=[],
                    threshold=80,
                    source_component_ids=None,
                )
            self.assertEqual(state.completed, {2})
            self.assertEqual(state.payload["updated"], 2)
            self.assertEqual(cast("Mock", batch.set_progress).call_args.args, (1,))
        finally:
            translation_continuation.reset(token)

        state = TranslationContinuation(
            json.loads(json.dumps(state.payload)), defer=True
        )
        token = translation_continuation.set(state)
        try:
            batch = self.make_batch()
            with patch(
                "weblate.trans.autotranslate.AutoTranslate",
                return_value=self.translation(),
            ) as constructor:
                batch.perform(
                    auto_source="mt",
                    engines=[],
                    threshold=80,
                    source_component_ids=None,
                )
            self.assertEqual(constructor.call_count, 1)
            self.assertEqual(constructor.call_args.kwargs["translation"].pk, 1)
            self.assertEqual(batch.updated, 4)
            self.assertEqual(state.completed, {1, 2})
            self.assertEqual(cast("Mock", batch.set_progress).call_args.args, (2,))
        finally:
            translation_continuation.reset(token)

    def test_removed_targets_complete_without_expanding_original_scope(self) -> None:
        state = TranslationContinuation(
            {"targets": [1, 3], "completed": [1]}, defer=True
        )
        batch = self.make_batch()
        state.restore(batch)
        self.assertEqual(batch.translations, [])
        self.assertEqual(state.completed, {1, 3})

    def test_continuation_preserves_errors_warnings_and_failure(self) -> None:
        batch = self.make_batch()
        batch.updated = 5
        batch.failure_message = "A provider failed"
        batch.errors = ["Provider diagnostic"]
        batch.add_warning("Warning", public_message="Public warning", component_ids=[7])
        state = TranslationContinuation({"targets": [1, 2]}, defer=True)
        state.checkpoint(batch, 1)
        restored = self.make_batch()
        TranslationContinuation(
            json.loads(json.dumps(state.payload)), defer=True
        ).restore(restored)
        self.assertEqual(restored.updated, 5)
        self.assertEqual(restored.errors, batch.errors)
        self.assertEqual(restored.failure_message, batch.failure_message)
        self.assertEqual(restored.get_warning_details(), batch.get_warning_details())

    def test_provider_progress_includes_completed_languages(self) -> None:
        state = TranslationContinuation(
            {"targets": [1, 2], "completed": [1]}, defer=True
        )
        state.task_meta = {"component": 3}
        auto = AutoTranslate.__new__(AutoTranslate)
        auto.translation = Mock(pk=2)
        auto.progress_steps = 10
        token = translation_continuation.set(state)
        task = SimpleNamespace(
            request=SimpleNamespace(id="task-id"), update_state=Mock()
        )
        try:
            with patch("weblate.trans.autotranslate.current_task", task):
                auto.set_progress(5)
                self.assertEqual(
                    task.update_state.call_args.kwargs["meta"],
                    {"component": 3, "progress": 75},
                )
                auto.set_progress(10)
                self.assertLess(
                    task.update_state.call_args.kwargs["meta"]["progress"], 100
                )
        finally:
            translation_continuation.reset(token)

    def test_coordination_retries_preserve_budget_and_continuation(self) -> None:
        def operation(**_options: object) -> None:
            state = cast("TranslationContinuation", translation_continuation.get())
            state.payload.update(targets=[1, 2], completed=[2], updated=2)
            raise AutomaticTranslationBusyError(1)

        task = SimpleNamespace(
            name=f"{operation.__module__}.{operation.__name__}",
            request=SimpleNamespace(id="task-id", is_eager=False, retries=100),
            retry=Mock(side_effect=Retry()),
        )
        with (
            patch("weblate.trans.coordination.current_task", task),
            self.assertRaises(Retry),
        ):
            translation_task(operation)(_translation_failures=2)
        options = task.retry.call_args.kwargs
        self.assertEqual(options["kwargs"]["_translation_failures"], 2)
        self.assertEqual(options["kwargs"]["_translation_resume"]["completed"], [2])
        self.assertGreaterEqual(options["countdown"], 30)
        self.assertLessEqual(options["countdown"], 60)
        self.assertIsNone(translation_continuation.get())

    def test_real_lock_failures_keep_three_retry_limit(self) -> None:
        error = WeblateLockTimeoutError("test", lock=Mock())

        def operation(**_options: object) -> None:
            raise error

        task = SimpleNamespace(
            name=f"{operation.__module__}.{operation.__name__}",
            request=SimpleNamespace(id="task-id", is_eager=False, retries=100),
            retry=Mock(side_effect=Retry()),
        )
        with patch("weblate.trans.coordination.current_task", task):
            with self.assertRaises(Retry):
                translation_task(operation)(_translation_failures=2)
            self.assertEqual(
                task.retry.call_args.kwargs["kwargs"]["_translation_failures"], 3
            )
            task.retry.reset_mock()
            with self.assertRaises(WeblateLockTimeoutError):
                translation_task(operation)(_translation_failures=3)
            task.retry.assert_not_called()
