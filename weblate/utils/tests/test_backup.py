# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shlex
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from contextlib import nullcontext
from typing import cast
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import override_settings

from weblate.utils.backup import (
    BackupError,
    BorgResult,
    backup,
    cleanup,
    get_paper_key,
    initialize,
    prune,
    run_borg,
    tag_cache_dirs,
)
from weblate.utils.data import data_path
from weblate.utils.tasks import database_backup, settings_backup
from weblate.utils.unittest import tempdir_setting


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
            patch("weblate.utils.backup.backup_lock", return_value=nullcontext()),
            patch("weblate.utils.backup.SSH_WRAPPER.create"),
            patch("weblate.utils.backup.report_error"),
            patch("weblate.utils.backup.subprocess.run", return_value=result),
        ):
            borg_result = run_borg(["create"])

        self.assertEqual(borg_result, BorgResult("warning output", returncode=1))

    def test_run_borg_disables_weak_crypto_warning(self) -> None:
        result = subprocess.CompletedProcess(["borg", "create"], 0, "")
        with (
            patch("weblate.utils.backup.backup_lock", return_value=nullcontext()),
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
            patch("weblate.utils.backup.backup_lock", return_value=nullcontext()),
            patch("weblate.utils.backup.SSH_WRAPPER.create"),
            patch("weblate.utils.backup.add_breadcrumb"),
            patch("weblate.utils.backup.report_error"),
            patch("weblate.utils.backup.subprocess.run", return_value=result),
            self.assertRaises(BackupError) as raised,
        ):
            run_borg(["create"])

        self.assertEqual(
            str(raised.exception),
            "Borg exited with status 2 without any output",
        )


class InitializeBackupTest(SimpleTestCase):
    def test_initialize_rejects_option_as_ssh_hostname(self) -> None:
        with (
            patch("weblate.utils.backup.add_host_key") as add_host_key,
            patch("weblate.utils.backup.run_borg") as run_borg,
            self.assertRaisesMessage(BackupError, "Invalid host name given!"),
        ):
            initialize("ssh://-f/etc/passwd:22/path", "key")

        add_host_key.assert_not_called()
        run_borg.assert_not_called()

    def test_initialize_accepts_single_label_ssh_hostname(self) -> None:
        with (
            patch("weblate.utils.backup.add_host_key") as add_host_key,
            patch(
                "weblate.utils.backup.run_borg", return_value=BorgResult(output="")
            ) as run_borg,
        ):
            initialize("ssh://backup/path", "key")

        add_host_key.assert_called_once_with(None, "backup", None)
        run_borg.assert_called_once_with(
            ["init", "--encryption", "repokey-blake2", "ssh://backup/path"],
            {"BORG_NEW_PASSPHRASE": "key"},
        )


class BackupCommandTest(SimpleTestCase):
    @override_settings(BORG_EXTRA_ARGS=())
    def test_backup_includes_changed_files_in_filter(self) -> None:
        with patch(
            "weblate.utils.backup.run_borg", return_value=BorgResult(output="")
        ) as mocked:
            backup("/backup/repository", "key")

        self.assertIn("ACME", mocked.call_args.args[0])
