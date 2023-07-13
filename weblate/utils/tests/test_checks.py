# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from weblate.utils.checks import is_celery_queue_long


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
        self.set_cache({int(time.monotonic() / 3600): {}})
        self.assertFalse(is_celery_queue_long())

    def test_past(self):
        self.set_cache({int(time.monotonic() / 3600) - 1: {}})
        self.assertFalse(is_celery_queue_long())

    def test_cleanup(self):
        hour = int(time.monotonic() / 3600)
        self.set_cache({i: {} for i in range(hour - 2, hour)})
        self.assertFalse(is_celery_queue_long())

    def test_trigger(self):
        with patch(
            "weblate.utils.checks.get_queue_stats", return_value={"celery": 1000}
        ):
            self.set_cache({int(time.monotonic() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.monotonic() / 3600) - 1: {"celery": 1000}})
            self.assertTrue(is_celery_queue_long())

    def test_translate(self):
        with patch(
            "weblate.utils.checks.get_queue_stats", return_value={"translate": 2000}
        ):
            self.set_cache({int(time.monotonic() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.monotonic() / 3600) - 1: {"translate": 100}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.monotonic() / 3600) - 1: {"translate": 2000}})
            self.assertTrue(is_celery_queue_long())
