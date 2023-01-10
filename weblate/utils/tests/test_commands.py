# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from glob import glob
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings

from weblate.trans.tests.utils import TempDirMixin


class CommandTests(SimpleTestCase, TempDirMixin):
    def setUp(self):
        self.create_temp()
        self.beat = os.path.join(self.tempdir, "beat")
        self.beat_db = os.path.join(self.tempdir, "beat.db")

    def tearDown(self):
        self.remove_temp()

    def check_beat(self):
        self.assertTrue(glob(self.beat + "*"))

    def test_none(self):
        with override_settings(CELERY_BEAT_SCHEDULE_FILENAME=self.beat):
            call_command("cleanup_celery")
        self.check_beat()

    def test_broken(self):
        for name in (self.beat, self.beat_db):
            with open(name, "wb") as handle:
                handle.write(b"\x00")
        with override_settings(CELERY_BEAT_SCHEDULE_FILENAME=self.beat):
            call_command("cleanup_celery")
        self.check_beat()

    def test_queues(self):
        output = StringIO()
        call_command("celery_queues", stdout=output)
        self.assertIn("celery:", output.getvalue())


class DBCommandTests(TestCase):
    def test_stats(self):
        output = StringIO()
        call_command("ensure_stats", stdout=output)
        self.assertEqual("", output.getvalue())
