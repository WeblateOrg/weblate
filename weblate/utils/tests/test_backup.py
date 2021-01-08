#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import os

from django.conf import settings
from django.test import TransactionTestCase
from django.test.utils import override_settings

from weblate.utils.backup import backup, get_paper_key, initialize, prune
from weblate.utils.data import data_dir
from weblate.utils.tasks import database_backup, settings_backup
from weblate.utils.unittest import tempdir_setting


class BackupTest(TransactionTestCase):
    @tempdir_setting("DATA_DIR")
    def test_settings_backup(self):
        settings_backup()
        filename = data_dir("backups", "settings-expanded.py")
        with open(filename) as handle:
            self.assertIn(settings.DATA_DIR, handle.read())

    @tempdir_setting("DATA_DIR")
    @tempdir_setting("BACKUP_DIR")
    def test_backup(self):
        initialize(settings.BACKUP_DIR, "key")
        output = get_paper_key(settings.BACKUP_DIR)
        self.assertIn("BORG PAPER KEY", output)
        output = backup(settings.BACKUP_DIR, "key")
        self.assertIn("Creating archive", output)
        output = prune(settings.BACKUP_DIR, "key")
        self.assertIn("Keeping archive", output)

    @tempdir_setting("DATA_DIR")
    def test_database_backup(self):
        database_backup()
        self.assertTrue(
            os.path.exists(os.path.join(settings.DATA_DIR, "backups", "database.sql"))
        )

    @tempdir_setting("DATA_DIR")
    @override_settings(DATABASE_BACKUP="compressed")
    def test_database_backup_compress(self):
        database_backup()
        self.assertTrue(
            os.path.exists(
                os.path.join(settings.DATA_DIR, "backups", "database.sql.gz")
            )
        )
