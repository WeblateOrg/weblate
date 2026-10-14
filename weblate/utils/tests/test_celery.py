# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

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
    store_published_task_metadata,
    store_task_metadata,
)
from weblate.utils.change_origin import (
    CHANGE_ORIGIN_HEADER,
    ChangeOrigin,
    change_origin,
    change_origin_context,
    get_change_origin,
)


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
