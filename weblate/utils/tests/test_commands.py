# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from glob import glob
import os

from django.core.management import call_command
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.trans.tests.utils import TempDirMixin


class CommandTests(SimpleTestCase, TempDirMixin):
    def setUp(self):
        self.create_temp()
        self.beat = os.path.join(self.tempdir, 'beat')
        self.beat_db = os.path.join(self.tempdir, 'beat.db')

    def tearDown(self):
        self.remove_temp()

    def check_beat(self):
        self.assertTrue(glob(self.beat + '*'))

    def test_none(self):
        with override_settings(CELERY_BEAT_SCHEDULE_FILENAME=self.beat):
            call_command('cleanup_celery')
        self.check_beat()

    def test_broken(self):
        for name in (self.beat, self.beat_db):
            with open(name, 'wb') as handle:
                handle.write(b'\x00')
        with override_settings(CELERY_BEAT_SCHEDULE_FILENAME=self.beat):
            call_command('cleanup_celery')
        self.check_beat()
