# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys

from django.test import SimpleTestCase

from weblate.utils.celery import (
    delete_task_metadata,
    get_task_metadata,
    store_task_metadata,
)


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
