# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.conf import settings
from django.test import TransactionTestCase
from django.test.utils import override_settings

from weblate.utils.backup import backup, cleanup, get_paper_key, initialize, prune
from weblate.utils.data import data_dir
from weblate.utils.tasks import database_backup, settings_backup
from weblate.utils.unittest import tempdir_setting


class BackupTest(TransactionTestCase):
    @tempdir_setting("DATA_DIR")
    def test_settings_backup(self) -> None:
        settings_backup()
        filename = data_dir("backups", "settings-expanded.py")
        with open(filename) as handle:
            self.assertIn(settings.DATA_DIR, handle.read())

    @tempdir_setting("DATA_DIR")
    @tempdir_setting("BACKUP_DIR")
    def test_backup(self) -> None:
        initialize(settings.BACKUP_DIR, "key")
        output = get_paper_key(settings.BACKUP_DIR)
        self.assertIn("BORG PAPER KEY", output)
        output = backup(settings.BACKUP_DIR, "key")
        self.assertIn("Creating archive", output)
        output = prune(settings.BACKUP_DIR, "key")
        self.assertIn("Keeping archive", output)
        cleanup(settings.BACKUP_DIR, "key", True)
        cleanup(settings.BACKUP_DIR, "key", False)

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
