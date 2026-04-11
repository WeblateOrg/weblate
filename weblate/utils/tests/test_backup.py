# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import subprocess  # noqa: S404
from contextlib import nullcontext
from typing import cast
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import override_settings

from weblate.utils.backup import (
    BackupError,
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
        output = get_paper_key(backup_dir)
        self.assertIn("BORG PAPER KEY", output)
        output = backup(backup_dir, "key")
        self.assertIn("Creating archive", output)
        output = prune(backup_dir, "key")
        self.assertIn("Keeping archive", output)
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


class RunBorgTest(SimpleTestCase):
    def test_run_borg_reports_silent_failure(self) -> None:
        error = subprocess.CalledProcessError(2, ["borg", "create"], output="")
        with (
            patch("weblate.utils.backup.backup_lock", return_value=nullcontext()),
            patch("weblate.utils.backup.SSH_WRAPPER.create"),
            patch("weblate.utils.backup.add_breadcrumb"),
            patch("weblate.utils.backup.report_error"),
            patch("weblate.utils.backup.subprocess.check_output", side_effect=error),
            self.assertRaises(BackupError) as raised,
        ):
            run_borg(["create"])

        self.assertEqual(
            str(raised.exception),
            "Borg exited with status 2 without any output",
        )
