# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from weblate.automation.context import automation_origin
from weblate.utils.celery import (
    OriginTask,
    app,
    delete_task_metadata,
    get_task_metadata,
    reset_automation_origin,
    reset_change_origin,
    restore_automation_origin,
    restore_change_origin,
    sanitize_task_result,
    store_published_task_metadata,
    store_task_metadata,
)
from weblate.utils.change_origin import (
    ACTING_USER_HEADER,
    CHANGE_ORIGIN_HEADER,
    ChangeOrigin,
    acting_user_context,
    change_origin,
    change_origin_context,
    get_acting_user,
    get_change_origin,
)
from weblate.utils.messages import store_task_completion_message

if TYPE_CHECKING:
    from celery import Celery


class TaskOriginTest(SimpleTestCase):
    def test_published_automation_matches_explicit_origin(self) -> None:
        headers = {
            CHANGE_ORIGIN_HEADER: {
                "scope": "automation",
                "automation": {"addon_id": 12, "activity_id": 34},
            }
        }
        with change_origin_context(
            {"scope": "automation", "automation": {"addon_id": 56, "activity_id": 78}}
        ):
            store_published_task_metadata(headers=headers)
        self.assertEqual(headers["weblate_automation_origin"], 34)

    def test_automation_header_restores_loop_protection(self) -> None:
        origin: ChangeOrigin = {
            "scope": "automation",
            "automation": {"addon_id": 12, "activity_id": 34},
        }
        task = SimpleNamespace(
            request=SimpleNamespace(
                headers={CHANGE_ORIGIN_HEADER: origin}, is_eager=False
            )
        )
        restore_automation_origin(task=task)
        restore_change_origin(task=task)
        try:
            self.assertEqual(get_change_origin(), origin)
            self.assertEqual(automation_origin.get(), 34)
        finally:
            reset_automation_origin(task=task)
            reset_change_origin(task=task)
        self.assertIsNone(automation_origin.get())
        self.assertIsNone(change_origin.get())

    def test_published_headers(self) -> None:
        headers: dict[str, object] = {}
        with change_origin_context({"scope": "api"}):
            store_published_task_metadata(headers=headers)
        self.assertEqual(headers[CHANGE_ORIGIN_HEADER], {"scope": "api"})

    def test_deferred_publication(self) -> None:
        task = OriginTask()
        for method in (task.delay_on_commit, task.apply_async_on_commit):
            with (
                self.subTest(method=method.__name__),
                patch("weblate.utils.celery.transaction.on_commit") as on_commit,
                patch("celery.contrib.django.task.DjangoTask.apply_async") as publish,
            ):
                with change_origin_context({"scope": "api"}):
                    method()
                on_commit.call_args.args[0]()
                self.assertEqual(
                    publish.call_args.kwargs["headers"][CHANGE_ORIGIN_HEADER],
                    {"scope": "api"},
                )
                self.assertIsNone(change_origin.get())

    def test_worker_cleanup_and_missing_headers(self) -> None:
        for headers, expected in (
            ({CHANGE_ORIGIN_HEADER: {"scope": "api"}}, "api"),
            ({}, "system"),
        ):
            with self.subTest(headers=headers), change_origin_context({"scope": "ui"}):
                task = SimpleNamespace(
                    request=SimpleNamespace(headers=headers, is_eager=False)
                )
                restore_change_origin(task=task)
                self.assertEqual(get_change_origin(), {"scope": expected})
                reset_change_origin(task=task)
                self.assertEqual(get_change_origin(), {"scope": "ui"})

    def test_eager_nested_tasks_and_retry(self) -> None:
        @app.task(name="weblate.utils.tests.origin_child")
        def child() -> ChangeOrigin:
            origin = get_change_origin()
            if automation := origin.get("automation"):
                self.assertEqual(automation_origin.get(), automation["activity_id"])
            return origin

        @app.task(bind=True, name="weblate.utils.tests.origin_parent")
        def parent(task: OriginTask) -> ChangeOrigin:
            if not task.request.retries:
                raise task.retry()
            return child.delay().get(disable_sync_subtasks=False)

        origins: list[ChangeOrigin] = [
            {"scope": "api"},
            {"scope": "automation", "automation": {"addon_id": 12, "activity_id": 34}},
        ]
        for origin in origins:
            with self.subTest(origin=origin), change_origin_context(origin):
                # Child .get() is safe here because both tasks execute eagerly.
                result = parent.apply_async(throw=False)
                self.assertEqual(result.get(disable_sync_subtasks=False), origin)
                self.assertEqual(get_change_origin(), origin)
        self.assertIsNone(change_origin.get())
        self.assertIsNone(automation_origin.get())


class TaskMetadataTest(SimpleTestCase):
    task_id = "01234567-89ab-cdef-0123-456789abcdef"

    def tearDown(self) -> None:
        delete_task_metadata(self.task_id)
        super().tearDown()

    def test_extended_metadata_is_only_stored_when_requested(self) -> None:
        store_task_metadata(self.task_id, component_id=1, user_id=2)

        self.assertEqual(
            get_task_metadata(self.task_id),
            {"component_id": 1, "translation_id": None, "user_id": 2},
        )

    def test_automatic_translation_warnings_without_reader(self) -> None:
        store_task_metadata(
            self.task_id, component_id=1, task_kind="automatic-translation"
        )
        result = {
            "warnings": ["Private source warning."],
            "_warning_details": [
                {
                    "message": "Private source warning.",
                    "public_message": "Source warning.",
                    "component_ids": [2],
                }
            ],
        }
        # No reader means no component query and no private details.
        self.assertEqual(
            sanitize_task_result(self.task_id, result),
            {"warnings": ["Source warning."]},
        )
        for warnings in (["Private source warning."], "Private source warning."):
            with self.subTest(warnings=warnings):
                self.assertEqual(
                    sanitize_task_result(self.task_id, {"warnings": warnings}),
                    {"warnings": ["Automatic translation reported a warning."]},
                )
        self.assertEqual(
            sanitize_task_result(self.task_id, {"progress": 42}), {"progress": 42}
        )

    def test_pending_results_do_not_query_components(self) -> None:
        store_task_metadata(
            self.task_id,
            component_ids=[1, 2, 3],
            translation_id=4,
            task_kind="repository-operation",
        )
        # SimpleTestCase rejects database queries, including repository lookups.
        for result in (
            None,
            {"progress": 42},
            {"completion_message": {"text": None}},
        ):
            with self.subTest(result=result):
                self.assertIs(sanitize_task_result(self.task_id, result), result)

    def test_automatic_translation_errors_without_provenance(self) -> None:
        for errors in (["Private diagnostic."], "Private diagnostic."):
            with self.subTest(errors=errors):
                result = {
                    "errors": errors,
                    "_error_details": [{"message": "Private diagnostic."}],
                }
                self.assertEqual(
                    sanitize_task_result(self.task_id, result),
                    {"errors": ["Automatic translation reported an error."]},
                )
        self.assertEqual(
            sanitize_task_result(self.task_id, {"errors": [], "_error_details": []}),
            {"errors": []},
        )

    def test_concurrent_updates_preserve_failure_dependencies(self) -> None:
        for dependencies_first in (False, True):
            with self.subTest(dependencies_first=dependencies_first):
                self.check_concurrent_metadata_merge(
                    dependencies_first=dependencies_first
                )

    def check_concurrent_metadata_merge(self, *, dependencies_first: bool) -> None:
        with (
            TemporaryDirectory() as data_dir,
            override_settings(
                DATA_DIR=data_dir,
                CACHES={
                    "default": {
                        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                        "LOCATION": "task-metadata-atomic-update",
                    }
                },
            ),
        ):
            delete_task_metadata(self.task_id)
            first_read = Event()
            release_first = Event()
            second_started = Event()
            second_read = Event()
            original_get = get_task_metadata
            updates = [
                partial(store_task_metadata, self.task_id, component_id=1),
                partial(
                    store_task_metadata,
                    self.task_id,
                    failure_component_ids=[2, 3],
                    failure_repository_ids=[3],
                ),
            ]
            if dependencies_first:
                updates.reverse()

            def read_snapshot(key: str) -> dict[str, object] | None:
                snapshot = original_get(key)
                if not first_read.is_set():
                    first_read.set()
                    if not release_first.wait(5):
                        msg = "First metadata writer was not released"
                        raise TimeoutError(msg)
                else:
                    second_read.set()
                return snapshot

            def second_update() -> None:
                second_started.set()
                updates[1]()

            with (
                ThreadPoolExecutor(max_workers=2) as executor,
                patch(
                    "weblate.utils.celery.get_task_metadata", side_effect=read_snapshot
                ),
            ):
                first = executor.submit(updates[0])
                try:
                    self.assertTrue(first_read.wait(5))
                    second = executor.submit(second_update)
                    self.assertTrue(second_started.wait(5))
                    # The second writer must wait before reading a stale snapshot.
                    self.assertFalse(second_read.wait(0.2))
                finally:
                    release_first.set()
                first.result(timeout=5)
                second.result(timeout=5)
            self.assertEqual(
                get_task_metadata(self.task_id),
                {
                    "component_id": 1,
                    "translation_id": None,
                    "failure_component_ids": [2, 3],
                    "failure_repository_ids": [3],
                },
            )

    def test_updates_preserve_repository_operation_metadata(self) -> None:
        store_task_metadata(
            self.task_id,
            component_ids=[1, 2],
            user_id=3,
            task_kind="repository-operation",
            cancellable=False,
        )

        store_task_metadata(self.task_id, component_id=1)

        self.assertEqual(
            get_task_metadata(self.task_id),
            {
                "component_id": 1,
                "component_ids": [1, 2],
                "translation_id": None,
                "user_id": 3,
                "task_kind": "repository-operation",
                "cancellable": False,
            },
        )


class TaskCompletionMessageTest(SimpleTestCase):
    def test_already_stored_message_does_not_sanitize_result(self) -> None:
        task = Mock(id="completed-task")
        request = SimpleNamespace(
            session={"task-completion-message-completed-task": True}
        )
        with patch("weblate.utils.celery.sanitize_task_result") as sanitize:
            store_task_completion_message(request, task)
        sanitize.assert_not_called()

    def test_previously_sanitized_result_is_reused(self) -> None:
        task = Mock(id="completed-task")
        request = SimpleNamespace(session={})
        result = {"completion_message": {"text": "Safe completion message."}}
        with (
            patch("weblate.utils.celery.sanitize_task_result") as sanitize,
            patch("weblate.utils.messages.add_message") as add_message,
        ):
            store_task_completion_message(request, task, result=result)
        sanitize.assert_not_called()
        add_message.assert_called_once()
        self.assertEqual(add_message.call_args.args[2], "Safe completion message.")
        self.assertTrue(request.session["task-completion-message-completed-task"])


class CeleryStartupTest(SimpleTestCase):
    @staticmethod
    def run_python(code: str, *, skip_checks: str | None = None) -> str:
        environment = os.environ.copy()
        environment["DJANGO_SETTINGS_MODULE"] = "weblate.settings_test"
        if skip_checks is None:
            environment.pop("CELERY_SKIP_CHECKS", None)
        else:
            environment["CELERY_SKIP_CHECKS"] = skip_checks
        result = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            env=environment,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()

    def test_task_discovery_avoids_heavy_startup_imports(self) -> None:
        output = self.run_python(
            """
import json
import os
import sys

from weblate.utils.celery import app

app.loader.import_default_modules()
print(json.dumps({
    "skip_checks": os.environ.get("CELERY_SKIP_CHECKS"),
    "cysignals_loaded": "cysignals" in sys.modules,
    "urls_loaded": "weblate.urls" in sys.modules,
    "matplotlib_loaded": "matplotlib" in sys.modules,
    "tesserocr_loaded": "tesserocr" in sys.modules,
}))
"""
        )

        self.assertEqual(
            json.loads(output),
            {
                "skip_checks": "1",
                "cysignals_loaded": True,
                "urls_loaded": False,
                "matplotlib_loaded": False,
                "tesserocr_loaded": False,
            },
        )

    def test_tesserocr_import_in_task_thread(self) -> None:
        output = self.run_python(
            """
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from importlib import import_module

from weblate.utils.celery import app

app.loader.import_default_modules()
with ThreadPoolExecutor(max_workers=1) as executor:
    executor.submit(import_module, "tesserocr").result()
print("loaded")
"""
        )

        self.assertEqual(output, "loaded")

    def test_url_loading_avoids_tesserocr_import(self) -> None:
        output = self.run_python(
            """
import sys
from importlib import import_module

from weblate.utils.celery import app

app.loader.import_default_modules()
import_module("weblate.urls")
print("tesserocr" in sys.modules)
"""
        )

        self.assertEqual(output, "False")

    def test_url_loading_before_worker_fork(self) -> None:
        output = self.run_python(
            """
import json
import sys

from celery.signals import worker_before_create_process
from weblate.utils.celery import app

app.loader.import_default_modules()
urls_loaded_before_fork = "weblate.urls" in sys.modules
worker_before_create_process.send(sender=app)
print(json.dumps({
    "urls_loaded_before_fork": urls_loaded_before_fork,
    "urls_loaded_after_fork": "weblate.urls" in sys.modules,
    "font_rendering_loaded": "weblate.fonts.render" in sys.modules,
    "matplotlib_loaded": "matplotlib" in sys.modules,
    "numpy_loaded": "numpy" in sys.modules,
    "tesserocr_loaded": "tesserocr" in sys.modules,
}))
"""
        )

        self.assertEqual(
            json.loads(output),
            {
                "urls_loaded_before_fork": False,
                "urls_loaded_after_fork": True,
                "font_rendering_loaded": False,
                "matplotlib_loaded": False,
                "numpy_loaded": False,
                "tesserocr_loaded": False,
            },
        )

    def test_explicit_check_configuration_is_preserved(self) -> None:
        output = self.run_python(
            """
import os

import weblate.utils.celery

print(repr(os.environ["CELERY_SKIP_CHECKS"]))
""",
            skip_checks="",
        )

        self.assertEqual(output, "''")


class TaskActorTest(SimpleTestCase):
    def setUp(self) -> None:
        from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]

        self.user = User(pk=101, username="actor")
        self.other_user = User(pk=102, username="other-actor")

    def test_deferred_publication(self) -> None:
        task = OriginTask()
        task.bind(cast("Celery", app))
        for method in (task.delay_on_commit, task.apply_async_on_commit):
            with (
                self.subTest(method=method.__name__),
                patch("weblate.utils.celery.transaction.on_commit") as on_commit,
                patch("celery.contrib.django.task.DjangoTask.apply_async") as publish,
            ):
                with acting_user_context(self.user):
                    method()
                with acting_user_context(self.other_user):
                    on_commit.call_args.args[0]()
                    self.assertIs(get_acting_user(), self.other_user)
                self.assertEqual(
                    publish.call_args.kwargs["headers"][ACTING_USER_HEADER],
                    self.user.pk,
                )
                self.assertIsNone(get_acting_user())

    def test_signature_publication_and_explicit_clear(self) -> None:
        with acting_user_context(self.user):
            headers: dict[str, object] = {}
            store_published_task_metadata(headers=headers)
            self.assertEqual(headers[ACTING_USER_HEADER], self.user.pk)
            headers = {ACTING_USER_HEADER: None}
            store_published_task_metadata(headers=headers)
            self.assertIsNone(headers[ACTING_USER_HEADER])

    def test_worker_actor_and_cleanup(self) -> None:
        task = OriginTask()
        task.bind(cast("Celery", app))
        for headers, expected in (
            ({ACTING_USER_HEADER: self.user.pk}, self.user),
            ({ACTING_USER_HEADER: None}, None),
            ({}, None),
        ):
            with (
                self.subTest(headers=headers),
                acting_user_context(self.other_user),
                patch("weblate.auth.models.User.objects.get", return_value=self.user),
                patch.object(task, "run", side_effect=get_acting_user),
            ):
                task.push_request(
                    headers=headers, called_directly=False, is_eager=False
                )
                try:
                    self.assertIs(task(), expected)
                finally:
                    task.pop_request()
                self.assertIs(get_acting_user(), self.other_user)

    def test_worker_rejects_invalid_or_deleted_actor(self) -> None:
        from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]

        task = OriginTask()
        task.bind(cast("Celery", app))
        for user_id, exception in (
            (True, ValueError),
            ("101", ValueError),
            (-1, ValueError),
            (101, User.DoesNotExist),
        ):
            with (
                self.subTest(user_id=user_id),
                acting_user_context(self.other_user),
                patch(
                    "weblate.auth.models.User.objects.get",
                    side_effect=User.DoesNotExist,
                ),
                patch.object(task, "run") as run,
            ):
                task.push_request(
                    headers={ACTING_USER_HEADER: user_id},
                    called_directly=False,
                    is_eager=False,
                )
                try:
                    with self.assertRaises(exception):
                        task()
                finally:
                    task.pop_request()
                run.assert_not_called()
                self.assertIs(get_acting_user(), self.other_user)

    def test_worker_exception_cleanup(self) -> None:
        task = OriginTask()
        task.bind(cast("Celery", app))
        with (
            acting_user_context(self.other_user),
            patch("weblate.auth.models.User.objects.get", return_value=self.user),
            patch.object(task, "run", side_effect=ValueError),
        ):
            task.push_request(
                headers={ACTING_USER_HEADER: self.user.pk},
                called_directly=False,
                is_eager=False,
            )
            try:
                with self.assertRaises(ValueError):
                    task()
            finally:
                task.pop_request()
            self.assertIs(get_acting_user(), self.other_user)

    def test_eager_nested_tasks_and_retry(self) -> None:
        @app.task(name="weblate.utils.tests.actor_child")
        def child() -> int | None:
            user = get_acting_user()
            return user.pk if user is not None else None

        @app.task(bind=True, name="weblate.utils.tests.actor_parent")
        def parent(task: OriginTask) -> int | None:
            if not task.request.retries:
                raise task.retry()
            return child.delay().get(disable_sync_subtasks=False)

        with (
            acting_user_context(self.user),
            patch("weblate.auth.models.User.objects.get", return_value=self.user),
        ):
            result = parent.apply_async(throw=False)
            self.assertEqual(result.get(disable_sync_subtasks=False), self.user.pk)
            self.assertIs(get_acting_user(), self.user)
        self.assertIsNone(get_acting_user())
