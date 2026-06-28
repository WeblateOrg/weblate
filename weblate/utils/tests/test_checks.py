# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from weakref import WeakSet

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.addons.base import BaseAddon
from weblate.utils.apps import (
    CACHE_EXEC_CHECK_PREFIX,
    check_class_loader,
    check_data_writable,
    check_database_size,
    check_errors,
    check_settings,
)
from weblate.utils.celery import is_celery_queue_long
from weblate.utils.classloader import ClassLoader
from weblate.utils.unittest import tempdir_setting


class CeleryQueueTest(SimpleTestCase):
    # ruff: ignore[mutable-class-default]
    databases = {"default"}

    @staticmethod
    def set_cache(value) -> None:
        cache.set("celery_queue_stats", value)

    def test_empty(self) -> None:
        self.set_cache({})
        self.assertFalse(is_celery_queue_long())
        # The current time should be in the cache
        self.assertEqual(len(cache.get("celery_queue_stats")), 1)

    def test_current(self) -> None:
        self.set_cache({int(time.time() / 3600): {}})
        self.assertFalse(is_celery_queue_long())

    def test_past(self) -> None:
        self.set_cache({int(time.time() / 3600) - 1: {}})
        self.assertFalse(is_celery_queue_long())

    def test_cleanup(self) -> None:
        hour = int(time.time() / 3600)
        self.set_cache({i: {} for i in range(hour - 2, hour)})
        self.assertFalse(is_celery_queue_long())

    def test_trigger(self) -> None:
        with patch(
            "weblate.utils.celery.get_queue_stats", return_value={"celery": 1000}
        ):
            self.set_cache({int(time.time() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"celery": 1000}})
            self.assertTrue(is_celery_queue_long())

    def test_translate(self) -> None:
        with patch(
            "weblate.utils.celery.get_queue_stats", return_value={"translate": 2000}
        ):
            self.set_cache({int(time.time() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"translate": 100}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"translate": 2000}})
            self.assertTrue(is_celery_queue_long())


class ClassLoaderCheckTestCase(SimpleTestCase):
    @override_settings(TEST_ADDONS=("weblate.addons.cleanup.CleanupAddon",))
    def test_load(self) -> None:
        loader = ClassLoader("TEST_ADDONS", construct=False, base_class=BaseAddon)
        loader.load_data()
        self.assertEqual(len(list(loader.keys())), 1)

    @override_settings(TEST_ADDONS="weblate.addons.cleanup.CleanupAddon")
    def test_invalid(self) -> None:
        old_instances = ClassLoader.instances
        ClassLoader.instances = WeakSet()
        try:
            loader = ClassLoader("TEST_ADDONS", construct=False, base_class=BaseAddon)
            # This operates on ClassLoader.instances
            errors = list(check_class_loader(app_configs=None, databases=None))
            self.assertEqual(len(errors), 1)
            self.assertIn(loader, ClassLoader.instances)
        finally:
            ClassLoader.instances = old_instances

    @override_settings(TEST_ADDONS=("weblate.addons.not_found",))
    def test_not_found(self) -> None:
        old_instances = ClassLoader.instances
        ClassLoader.instances = WeakSet()
        try:
            loader = ClassLoader("TEST_ADDONS", construct=False, base_class=BaseAddon)
            # This operates on ClassLoader.instances
            errors = list(check_class_loader(app_configs=None, databases=None))
            self.assertEqual(len(errors), 1)
            self.assertIn("does not define a 'not_found' class", errors[0].msg)
            self.assertIn(loader, ClassLoader.instances)
        finally:
            ClassLoader.instances = old_instances


class DataWritableCheckTestCase(SimpleTestCase):
    @staticmethod
    def get_cache_probes() -> list[Path]:
        return list(
            (Path(settings.CACHE_DIR) / "ssh").glob(f"{CACHE_EXEC_CHECK_PREFIX}*")
        )

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_cache_dir_executable(self) -> None:
        errors = list(check_data_writable(app_configs=None, databases=None))

        self.assertFalse(any(error.id == "weblate.C044" for error in errors))
        self.assertEqual(self.get_cache_probes(), [])

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_cache_dir_execution_permission_error(self) -> None:
        with patch(
            "weblate.utils.apps.subprocess.run",
            side_effect=PermissionError("permission denied"),
        ):
            errors = list(check_data_writable(app_configs=None, databases=None))

        self.assertTrue(any(error.id == "weblate.C044" for error in errors))
        self.assertEqual(self.get_cache_probes(), [])

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_cache_dir_execution_failure(self) -> None:
        with patch(
            "weblate.utils.apps.subprocess.run",
            return_value=Mock(returncode=126),
        ):
            errors = list(check_data_writable(app_configs=None, databases=None))

        self.assertTrue(any(error.id == "weblate.C044" for error in errors))
        self.assertEqual(self.get_cache_probes(), [])


class DatabaseSizeCheckTestCase(SimpleTestCase):
    @patch(
        "weblate.utils.apps.get_database_disk_usage",
        return_value=SimpleNamespace(free=123457),
    )
    @patch("weblate.utils.apps.get_database_size", return_value=123456)
    @patch("weblate.utils.apps.connections")
    def test_database_size_available(
        self, connections_mock, database_size_mock, disk_usage_mock
    ) -> None:
        connections_mock.__getitem__.return_value.vendor = "postgresql"

        errors = list(check_database_size(app_configs=None, databases=None))

        self.assertFalse(
            any(error.id in {"weblate.C045", "weblate.C046"} for error in errors)
        )
        database_size_mock.assert_called_once_with()
        disk_usage_mock.assert_called_once_with()

    @patch(
        "weblate.utils.apps.get_database_disk_usage",
        return_value=SimpleNamespace(free=123455),
    )
    @patch("weblate.utils.apps.get_database_size", return_value=123456)
    @patch("weblate.utils.apps.connections")
    def test_database_size_not_enough_space(
        self, connections_mock, database_size_mock, disk_usage_mock
    ) -> None:
        connections_mock.__getitem__.return_value.vendor = "postgresql"

        errors = list(check_database_size(app_configs=None, databases=None))

        self.assertTrue(any(error.id == "weblate.C046" for error in errors))
        database_size_mock.assert_called_once_with()
        disk_usage_mock.assert_called_once_with()

    @patch("weblate.utils.apps.get_database_disk_usage", return_value=None)
    @patch("weblate.utils.apps.get_database_size", return_value=123456)
    @patch("weblate.utils.apps.connections")
    def test_database_size_disk_usage_unavailable(
        self, connections_mock, database_size_mock, disk_usage_mock
    ) -> None:
        connections_mock.__getitem__.return_value.vendor = "postgresql"

        errors = list(check_database_size(app_configs=None, databases=None))

        self.assertFalse(any(error.id == "weblate.C046" for error in errors))
        database_size_mock.assert_called_once_with()
        disk_usage_mock.assert_called_once_with()

    @patch("weblate.utils.apps.get_database_size", return_value=None)
    @patch("weblate.utils.apps.connections")
    def test_database_size_unavailable(
        self, connections_mock, database_size_mock
    ) -> None:
        connections_mock.__getitem__.return_value.vendor = "postgresql"

        errors = list(check_database_size(app_configs=None, databases=None))

        self.assertTrue(any(error.id == "weblate.C045" for error in errors))
        database_size_mock.assert_called_once_with()

    @patch("weblate.utils.apps.get_database_size")
    @patch("weblate.utils.apps.connections")
    def test_database_size_non_postgresql(
        self, connections_mock, database_size_mock
    ) -> None:
        connections_mock.__getitem__.return_value.vendor = "sqlite"

        errors = list(check_database_size(app_configs=None, databases=None))

        self.assertFalse(any(error.id == "weblate.C045" for error in errors))
        database_size_mock.assert_not_called()


class SettingsCheckTestCase(SimpleTestCase):
    @override_settings(ADMINS=["Weblate Admin <weblate@example.com>"])
    def test_default_admin_string_email(self) -> None:
        errors = list(check_settings(app_configs=None, databases=None))
        self.assertTrue(any(error.id == "weblate.E011" for error in errors))

    @override_settings(ADMINS=[("Weblate Admin", "weblate@example.com")])
    def test_default_admin_tuple_email(self) -> None:
        errors = list(check_settings(app_configs=None, databases=None))
        self.assertTrue(any(error.id == "weblate.E011" for error in errors))


class ErrorCollectionCheckTestCase(SimpleTestCase):
    @override_settings(SENTRY_DSN=None, GOOGLE_CLOUD_ERROR_REPORTING=None)
    def test_error_collection_missing(self) -> None:
        errors = list(check_errors(app_configs=None, databases=None))

        self.assertTrue(any(error.id == "weblate.I021" for error in errors))

    @override_settings(SENTRY_DSN=None, GOOGLE_CLOUD_ERROR_REPORTING={})
    def test_google_cloud_error_reporting_configured(self) -> None:
        errors = list(check_errors(app_configs=None, databases=None))

        self.assertFalse(any(error.id == "weblate.I021" for error in errors))
