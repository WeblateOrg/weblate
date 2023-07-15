# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from weblate.trans.tests.utils import TempDirMixin


class CommandTests(SimpleTestCase, TempDirMixin):
    def test_queues(self):
        output = StringIO()
        call_command("celery_queues", stdout=output)
        self.assertIn("celery:", output.getvalue())


class DBCommandTests(TestCase):
    def test_stats(self):
        output = StringIO()
        call_command("ensure_stats", stdout=output)
        self.assertEqual("", output.getvalue())
