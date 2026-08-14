# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock, patch
from weakref import WeakSet

import httpx2
from django.conf import settings
from django.core.cache import cache
from django.core.checks import Warning as DjangoWarning
from django.db import DatabaseError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.addons.base import BaseAddon
from weblate.utils.apps import (
    CACHE_EXEC_CHECK_PREFIX,
    check_class_loader,
    check_data_writable,
    check_database,
    check_database_size,
    check_errors,
    check_filesystem_latency,
    check_settings,
    check_version,
)
from weblate.utils.celery import is_celery_queue_long
from weblate.utils.classloader import ClassLoader
from weblate.utils.filesystem import (
    FILESYSTEM_LATENCY_PREFIX,
    filesystem_latency_snapshot,
    get_filesystem_latencies,
    measure_filesystem_latency,
)
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
        self.assertTrue((Path(settings.CACHE_DIR) / "matplotlib").is_dir())

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_matplotlib_cache_path_creation_error(self) -> None:
        matplotlib_cache = Path(settings.CACHE_DIR) / "matplotlib"
        matplotlib_cache.write_text("not a directory", encoding="utf-8")

        errors = list(check_data_writable(app_configs=None, databases=None))

        self.assertTrue(
            any(
                error.id == "weblate.E002" and str(matplotlib_cache) in error.msg
                for error in errors
            )
        )

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


class FilesystemLatencyTestCase(SimpleTestCase):
    @tempdir_setting("DATA_DIR")
    def test_measure_filesystem_latency(self) -> None:
        timestamps: list[int] = []
        current = 0
        for duration in range(1, 26):
            timestamps.extend((current, current + duration * 1_000_000))
            current += (duration + 1) * 1_000_000

        lookups: list[Path] = []

        def missing(path: Path) -> None:
            lookups.append(path)
            raise FileNotFoundError

        with (
            patch("weblate.utils.filesystem.monotonic_ns", side_effect=timestamps),
            patch(
                "pathlib.Path.lstat",
                autospec=True,
                side_effect=missing,
            ),
        ):
            latency = measure_filesystem_latency(Path(settings.DATA_DIR))

        self.assertEqual(latency, 13.0)
        self.assertEqual(len(lookups), 25)
        self.assertEqual(len({path.name for path in lookups}), 25)
        self.assertTrue(
            all(path.name.startswith(FILESYSTEM_LATENCY_PREFIX) for path in lookups)
        )

    @tempdir_setting("DATA_DIR")
    @patch(
        "pathlib.Path.lstat",
        autospec=True,
        side_effect=PermissionError,
    )
    def test_measure_filesystem_latency_error(self, lstat_mock) -> None:
        self.assertIsNone(measure_filesystem_latency(Path(settings.DATA_DIR)))
        lstat_mock.assert_called_once()

    @patch(
        "weblate.utils.filesystem.measure_filesystem_latencies",
        return_value={"DATA_DIR": 1.0, "CACHE_DIR": 2.0},
    )
    def test_filesystem_latency_snapshot(self, measure_mock) -> None:
        with filesystem_latency_snapshot() as snapshot:
            self.assertIs(get_filesystem_latencies(), snapshot)
            self.assertIs(get_filesystem_latencies(), snapshot)

        self.assertEqual(snapshot, {"DATA_DIR": 1.0, "CACHE_DIR": 2.0})
        measure_mock.assert_called_once_with()

    @patch(
        "weblate.utils.apps.get_filesystem_latency_paths",
        return_value={
            "DATA_DIR": Path("/data/vcs"),
            "CACHE_DIR": Path("/cache"),
        },
    )
    @patch(
        "weblate.utils.apps.get_filesystem_latencies",
        return_value={"DATA_DIR": 10.0, "CACHE_DIR": None},
    )
    def test_filesystem_latency_acceptable(self, latency_mock, paths_mock) -> None:
        self.assertEqual(
            list(check_filesystem_latency(app_configs=None, databases=None)), []
        )
        latency_mock.assert_called_once_with()
        paths_mock.assert_called_once_with()

    @patch(
        "weblate.utils.apps.get_filesystem_latency_paths",
        return_value={
            "DATA_DIR": Path("/data/vcs"),
            "CACHE_DIR": Path("/cache"),
        },
    )
    @patch(
        "weblate.utils.apps.get_filesystem_latencies",
        return_value={"DATA_DIR": 10.1, "CACHE_DIR": 20.0},
    )
    def test_filesystem_latency_slow(self, latency_mock, paths_mock) -> None:
        errors = list(check_filesystem_latency(app_configs=None, databases=None))

        self.assertEqual(len(errors), 2)
        self.assertTrue(all(isinstance(error, DjangoWarning) for error in errors))
        self.assertTrue(all(error.id == "weblate.W048" for error in errors))
        self.assertIn("/data/vcs", errors[0].msg)
        self.assertIn("10.1 milliseconds", errors[0].msg)
        self.assertIn("DATA_DIR", errors[0].msg)
        self.assertIn("/cache", errors[1].msg)
        self.assertIn("20 milliseconds", errors[1].msg)
        self.assertIn("CACHE_DIR", errors[1].msg)
        latency_mock.assert_called_once_with()
        paths_mock.assert_called_once_with()


class DatabaseSizeCheckTestCase(SimpleTestCase):
    @patch("weblate.utils.apps.get_database_size", return_value=123456)
    @patch("weblate.utils.apps.connections")
    def test_database_size_available(
        self,
        connections_mock,
        database_size_mock,
    ) -> None:
        connections_mock.__getitem__.return_value.vendor = "postgresql"

        errors = list(check_database_size(app_configs=None, databases=None))

        self.assertFalse(any(error.id == "weblate.C045" for error in errors))
        database_size_mock.assert_called_once_with()

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


class DatabaseStatisticsCheckTestCase(SimpleTestCase):
    @patch("weblate.utils.apps.measure_database_latency", return_value=1)
    @patch("weblate.utils.apps.get_invalid_database_statistics", return_value=[])
    def test_valid_statistics(self, statistics_mock, latency_mock) -> None:
        errors = list(check_database(app_configs=None, databases=None))

        self.assertFalse(any(error.id == "weblate.C047" for error in errors))
        statistics_mock.assert_called_once_with()
        latency_mock.assert_called_once_with()

    @patch("weblate.utils.apps.measure_database_latency", return_value=1)
    @patch(
        "weblate.utils.apps.get_invalid_database_statistics",
        return_value=["public.trans_unit"],
    )
    def test_invalid_statistics(self, statistics_mock, latency_mock) -> None:
        errors = list(check_database(app_configs=None, databases=None))

        error = next(error for error in errors if error.id == "weblate.C047")
        self.assertIn("public.trans_unit", error.msg)
        self.assertIn("Run ANALYZE", error.msg)
        statistics_mock.assert_called_once_with()
        latency_mock.assert_called_once_with()

    @patch("weblate.utils.apps.measure_database_latency", return_value=1)
    @patch(
        "weblate.utils.apps.get_invalid_database_statistics",
        side_effect=DatabaseError("catalog query failed"),
    )
    def test_statistics_database_error(self, statistics_mock, latency_mock) -> None:
        errors = list(check_database(app_configs=None, databases=None))

        error = next(error for error in errors if error.id == "weblate.C037")
        self.assertIn("catalog query failed", error.msg)
        statistics_mock.assert_called_once_with()
        latency_mock.assert_called_once_with()


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


class VersionCheckTestCase(SimpleTestCase):
    @patch(
        "weblate.utils.apps.get_latest_version",
        side_effect=httpx2.ConnectError("PyPI unavailable"),
    )
    def test_http_error_is_ignored(self, get_latest_version) -> None:
        errors = list(check_version(app_configs=None, databases=None))

        self.assertEqual(errors, [])
        get_latest_version.assert_called_once_with()
