# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from contextlib import contextmanager, nullcontext
from typing import cast
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import override_settings

from weblate.utils.backup import (
    BACKUP_LOCK_KEY,
    BackupError,
    BorgResult,
    backup,
    backup_lock,
    cleanup,
    get_paper_key,
    initialize,
    prune,
    run_borg,
    tag_cache_dirs,
)
from weblate.utils.data import data_path
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.tasks import (
    database_backup,
    run_backup_preparation,
    settings_backup,
)
from weblate.utils.unittest import tempdir_setting
from weblate.wladmin.models import BackupService


class BackupTest(TransactionTestCase):
    @tempdir_setting("DATA_DIR")
    def test_settings_backup(self) -> None:
        settings_backup()
        filename = data_path("backups") / "settings-expanded.py"
        self.assertIn(settings.DATA_DIR, filename.read_text())

    @tempdir_setting("DATA_DIR")
    @tempdir_setting("BACKUP_DIR")
    def test_backup(self) -> None:
        backup_dir = cast("str", settings.BACKUP_DIR)  # type: ignore[misc]
        initialize(backup_dir, "key")
        paper_key = get_paper_key(backup_dir)
        self.assertIn("BORG PAPER KEY", paper_key)
        backup_result = backup(backup_dir, "key")
        self.assertIn("Creating archive", backup_result.output)
        prune_result = prune(backup_dir, "key")
        self.assertIn("Keeping archive", prune_result.output)
        cleanup(backup_dir, "key", True)
        cleanup(backup_dir, "key", False)

    @tempdir_setting("DATA_DIR")
    def test_database_backup(self) -> None:
        database_backup()
        self.assertTrue(
            os.path.exists(os.path.join(settings.DATA_DIR, "backups", "database.sql"))
        )

    @tempdir_setting("DATA_DIR")
    @override_settings(DATABASE_BACKUP="compressed")
    def test_database_backup_compress(self) -> None:
        database_backup()
        self.assertTrue(
            os.path.exists(
                os.path.join(settings.DATA_DIR, "backups", "database.sql.gz")
            )
        )

    @tempdir_setting("DATA_DIR")
    def test_database_backup_logs_success_for_enabled_services(self) -> None:
        enabled = BackupService.objects.create(
            repository="/backup/enabled", paperkey="paper"
        )
        disabled = BackupService.objects.create(
            repository="/backup/disabled", paperkey="paper", enabled=False
        )

        with patch("weblate.utils.tasks.subprocess.run"):
            database_backup()

        log = enabled.backuplog_set.get()
        self.assertEqual(log.event, "database")
        self.assertEqual(log.log, "Database dump completed successfully.")
        self.assertFalse(disabled.backuplog_set.exists())

    @tempdir_setting("DATA_DIR")
    def test_database_backup_logs_pg_dump_failure(self) -> None:
        enabled = BackupService.objects.create(
            repository="/backup/enabled", paperkey="paper"
        )
        disabled = BackupService.objects.create(
            repository="/backup/disabled", paperkey="paper", enabled=False
        )
        error = subprocess.CalledProcessError(
            1,
            ["pg_dump"],
            stderr="pg_dump: error: server version mismatch",
        )

        with (
            patch("weblate.utils.tasks.subprocess.run", side_effect=error),
            patch("weblate.utils.tasks.add_breadcrumb") as add_breadcrumb,
            patch("weblate.utils.tasks.report_error") as report_error,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            database_backup([disabled.pk])

        log = enabled.backuplog_set.get()
        self.assertEqual(log.event, "database-error")
        self.assertEqual(log.log, "pg_dump: error: server version mismatch")
        self.assertEqual(disabled.backuplog_set.get().event, "database-error")
        add_breadcrumb.assert_called_once()
        report_error.assert_called_once_with("Database backup failed")

    @override_settings(DATABASE_BACKUP="none")
    def test_disabled_database_backup_does_not_log(self) -> None:
        service = BackupService.objects.create(repository="/backup", paperkey="paper")

        with patch("weblate.utils.tasks.subprocess.run") as run:
            database_backup()

        run.assert_not_called()
        self.assertFalse(service.backuplog_set.exists())

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_tag_cache_dirs_marks_ssh_wrapper_cache(self) -> None:
        ssh_cache_dir = data_path("cache") / "ssh"
        ssh_cache_dir.mkdir(parents=True)

        tag_cache_dirs()

        self.assertTrue((ssh_cache_dir / "CACHEDIR.TAG").exists())

    @tempdir_setting("CACHE_DIR")
    @tempdir_setting("DATA_DIR")
    def test_tag_cache_dirs_marks_matplotlib_cache(self) -> None:
        matplotlib_cache_dir = data_path("cache") / "matplotlib"
        matplotlib_cache_dir.mkdir(parents=True)

        tag_cache_dirs()

        self.assertTrue((matplotlib_cache_dir / "CACHEDIR.TAG").exists())


class RunBorgTest(SimpleTestCase):
    def test_run_borg_returns_warning_result(self) -> None:
        result = subprocess.CompletedProcess(["borg", "create"], 1, "warning output")
        with (
            patch("weblate.utils.backup.SSH_WRAPPER.create"),
            patch("weblate.utils.backup.report_error"),
            patch("weblate.utils.backup.subprocess.run", return_value=result),
        ):
            borg_result = run_borg(["create"])

        self.assertEqual(borg_result, BorgResult("warning output", returncode=1))

    def test_run_borg_disables_weak_crypto_warning(self) -> None:
        result = subprocess.CompletedProcess(["borg", "create"], 0, "")
        with (
            patch("weblate.utils.backup.SSH_WRAPPER.create"),
            patch("weblate.utils.backup.subprocess.run", return_value=result) as run,
        ):
            run_borg(["create"])

        borg_command = run.call_args.args[0]
        ssh_command = shlex.split(borg_command[2])
        self.assertEqual(borg_command[:2], ["borg", "--rsh"])
        self.assertEqual(
            ssh_command[-4:],
            [
                "-o",
                "IgnoreUnknown=WarnWeakCrypto",
                "-o",
                "WarnWeakCrypto=no-pq-kex",
            ],
        )

    def test_run_borg_reports_silent_failure(self) -> None:
        result = subprocess.CompletedProcess(["borg", "create"], 2, "")
        with (
            patch("weblate.utils.backup.SSH_WRAPPER.create"),
            patch("weblate.utils.backup.add_breadcrumb"),
            patch("weblate.utils.backup.report_message") as report_message,
            patch("weblate.utils.backup.subprocess.run", return_value=result),
            self.assertRaises(BackupError) as raised,
        ):
            run_borg(["create"])

        self.assertEqual(
            str(raised.exception),
            "Borg exited with status 2 without any output",
        )
        report_message.assert_called_once_with("Borg failed")


class BackupLockTest(SimpleTestCase):
    def test_shared_lock_uses_postgresql_advisory_lock(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        atomic = MagicMock()

        with (
            patch("weblate.utils.backup.connection", database_connection),
            patch("weblate.utils.backup.transaction.atomic", return_value=atomic),
            backup_lock(shared=True),
        ):
            pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock_shared(%s)", [BACKUP_LOCK_KEY]
        )
        atomic.__enter__.assert_called_once_with()
        atomic.__exit__.assert_called_once_with(None, None, None)

    def test_transaction_rolls_back_after_exception(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        atomic = MagicMock()

        with (
            patch("weblate.utils.backup.connection", database_connection),
            patch("weblate.utils.backup.transaction.atomic", return_value=atomic),
            self.assertRaisesRegex(RuntimeError, "backup failed"),
            backup_lock(),
        ):
            msg = "backup failed"
            raise RuntimeError(msg)

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock(%s)", [BACKUP_LOCK_KEY]
        )
        exit_args = atomic.__exit__.call_args.args
        self.assertIs(exit_args[0], RuntimeError)
        self.assertEqual(str(exit_args[1]), "backup failed")

    def test_exclusive_lock_times_out(self) -> None:
        cursor = MagicMock()
        cursor.fetchone.return_value = (False,)
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor_context
        atomic = MagicMock()

        with (
            patch("weblate.utils.backup.connection", database_connection),
            patch("weblate.utils.backup.transaction.atomic", return_value=atomic),
            self.assertRaisesRegex(WeblateLockTimeoutError, "could not be acquired"),
            backup_lock(timeout=0),
        ):
            pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_try_advisory_xact_lock(%s)", [BACKUP_LOCK_KEY]
        )


class BackupLockDatabaseTest(TransactionTestCase):
    def test_shared_locks_coexist_and_block_exclusive_lock(self) -> None:
        other_connection = connection.copy(alias="default")
        try:
            other_connection.set_autocommit(False)
            with backup_lock(shared=True), other_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock_shared(%s)", [BACKUP_LOCK_KEY]
                )
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s)", [BACKUP_LOCK_KEY]
                )
                self.assertFalse(cursor.fetchone()[0])
            other_connection.rollback()

            with other_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s)", [BACKUP_LOCK_KEY]
                )
                self.assertTrue(cursor.fetchone()[0])
            other_connection.rollback()
        finally:
            other_connection.close()

    def test_exception_releases_exclusive_lock(self) -> None:
        other_connection = connection.copy(alias="default")
        try:
            other_connection.set_autocommit(False)
            with self.assertRaisesRegex(RuntimeError, "backup failed"), backup_lock():
                msg = "backup failed"
                raise RuntimeError(msg)

            with other_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_xact_lock(%s)", [BACKUP_LOCK_KEY]
                )
                self.assertTrue(cursor.fetchone()[0])
            other_connection.rollback()
        finally:
            other_connection.close()


class BackupPreparationTest(SimpleTestCase):
    def test_updates_all_files_under_one_exclusive_lock(self) -> None:
        operations: list[str | tuple[str, list[int] | None]] = []

        @contextmanager
        def tracked_lock():
            operations.append("lock-enter")
            try:
                yield
            finally:
                operations.append("lock-exit")

        def track_database_backup() -> bool:
            operations.append("database")
            return True

        with (
            patch("weblate.utils.tasks.backup_lock", side_effect=tracked_lock),
            patch(
                "weblate.utils.tasks._run_settings_backup",
                side_effect=lambda: operations.append("settings"),
            ),
            patch(
                "weblate.utils.tasks._run_database_backup",
                side_effect=track_database_backup,
            ),
            patch(
                "weblate.utils.tasks._record_database_backup_success",
                side_effect=lambda service_ids: operations.append(
                    ("database-log", service_ids)
                ),
            ),
        ):
            run_backup_preparation([7])

        self.assertEqual(
            operations,
            [
                "lock-enter",
                "settings",
                "database",
                "lock-exit",
                ("database-log", [7]),
            ],
        )

    def test_database_failure_is_recorded_after_lock_release(self) -> None:
        operations = []
        error = subprocess.CalledProcessError(
            1,
            ["pg_dump"],
            stderr="pg_dump failed",
        )

        @contextmanager
        def tracked_lock():
            operations.append("lock-enter")
            try:
                yield
            finally:
                operations.append("lock-exit")

        def record_error(*_args: object) -> None:
            operations.append("database-log")

        with (
            patch("weblate.utils.tasks.backup_lock", side_effect=tracked_lock),
            patch("weblate.utils.tasks._run_settings_backup"),
            patch("weblate.utils.tasks.subprocess.run", side_effect=error),
            patch(
                "weblate.utils.tasks._record_database_backup_error",
                side_effect=record_error,
            ) as record,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            run_backup_preparation([7])

        self.assertEqual(operations, ["lock-enter", "lock-exit", "database-log"])
        record.assert_called_once_with(error, [7])


class InitializeBackupTest(SimpleTestCase):
    def test_initialize_rejects_option_as_ssh_hostname(self) -> None:
        with (
            patch("weblate.utils.backup.add_host_key") as add_host_key,
            patch("weblate.utils.backup.run_borg") as mock_run_borg,
            self.assertRaisesMessage(BackupError, "Invalid host name given!"),
        ):
            initialize("ssh://-f/etc/passwd:22/path", "key")

        add_host_key.assert_not_called()
        mock_run_borg.assert_not_called()

    def test_initialize_accepts_single_label_ssh_hostname(self) -> None:
        with (
            patch("weblate.utils.backup.add_host_key") as add_host_key,
            patch(
                "weblate.utils.backup.run_borg", return_value=BorgResult(output="")
            ) as mock_run_borg,
        ):
            initialize("ssh://backup/path", "key")

        add_host_key.assert_called_once_with(None, "backup", None)
        mock_run_borg.assert_called_once_with(
            ["init", "--encryption", "repokey-blake2", "ssh://backup/path"],
            {"BORG_NEW_PASSPHRASE": "key"},
        )


class BackupCommandTest(SimpleTestCase):
    @override_settings(BORG_EXTRA_ARGS=())
    def test_backup_includes_changed_files_in_filter(self) -> None:
        with (
            patch(
                "weblate.utils.backup.backup_lock", return_value=nullcontext()
            ) as lock,
            patch(
                "weblate.utils.backup.run_borg", return_value=BorgResult(output="")
            ) as mocked,
        ):
            backup("/backup/repository", "key")

        lock.assert_called_once_with(shared=True)
        self.assertIn("ACME", mocked.call_args.args[0])
