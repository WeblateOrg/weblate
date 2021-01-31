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


import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from ..checks import is_celery_queue_long


class CeleryQueueTest(SimpleTestCase):
    databases = ["default"]

    @staticmethod
    def set_cache(value):
        cache.set("celery_queue_stats", value)

    def test_empty(self):
        self.set_cache({})
        self.assertFalse(is_celery_queue_long())
        # The current time should be in the cache
        self.assertEqual(len(cache.get("celery_queue_stats")), 1)

    def test_current(self):
        self.set_cache({int(time.time() / 3600): {}})
        self.assertFalse(is_celery_queue_long())

    def test_past(self):
        self.set_cache({int(time.time() / 3600) - 1: {}})
        self.assertFalse(is_celery_queue_long())

    def test_cleanup(self):
        hour = int(time.time() / 3600)
        self.set_cache({i: {} for i in range(hour - 2, hour)})
        self.assertFalse(is_celery_queue_long())

    def test_trigger(self):
        with patch(
            "weblate.utils.checks.get_queue_stats", return_value={"celery": 1000}
        ):
            self.set_cache({int(time.time() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"celery": 1000}})
            self.assertTrue(is_celery_queue_long())

    def test_translate(self):
        with patch(
            "weblate.utils.checks.get_queue_stats", return_value={"translate": 2000}
        ):
            self.set_cache({int(time.time() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"translate": 100}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"translate": 2000}})
            self.assertTrue(is_celery_queue_long())
