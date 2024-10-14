# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.addons.base import BaseAddon
from weblate.utils.apps import check_class_loader
from weblate.utils.celery import is_celery_queue_long
from weblate.utils.classloader import ClassLoader


class CeleryQueueTest(SimpleTestCase):
    databases = {"default"}

    @staticmethod
    def set_cache(value) -> None:
        cache.set("celery_queue_stats", value)

    def test_empty(self) -> None:
        self.set_cache({})
        self.assertFalse(is_celery_queue_long())
        # The current time should be in the cache
        self.assertEqual(len(cache.get("celery_queue_stats")), 1)

    def test_current(self) -> None:
        self.set_cache({int(time.time() / 3600): {}})
        self.assertFalse(is_celery_queue_long())

    def test_past(self) -> None:
        self.set_cache({int(time.time() / 3600) - 1: {}})
        self.assertFalse(is_celery_queue_long())

    def test_cleanup(self) -> None:
        hour = int(time.time() / 3600)
        self.set_cache({i: {} for i in range(hour - 2, hour)})
        self.assertFalse(is_celery_queue_long())

    def test_trigger(self) -> None:
        with patch(
            "weblate.utils.celery.get_queue_stats", return_value={"celery": 1000}
        ):
            self.set_cache({int(time.time() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"celery": 1000}})
            self.assertTrue(is_celery_queue_long())

    def test_translate(self) -> None:
        with patch(
            "weblate.utils.celery.get_queue_stats", return_value={"translate": 2000}
        ):
            self.set_cache({int(time.time() / 3600) - 1: {}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"translate": 100}})
            self.assertFalse(is_celery_queue_long())
            self.set_cache({int(time.time() / 3600) - 1: {"translate": 2000}})
            self.assertTrue(is_celery_queue_long())


class ClassLoaderCheckTestCase(SimpleTestCase):
    @override_settings(TEST_ADDONS=("weblate.addons.cleanup.CleanupAddon",))
    def test_load(self) -> None:
        loader = ClassLoader("TEST_ADDONS", construct=False, base_class=BaseAddon)
        loader.load_data()
        self.assertEqual(len(list(loader.keys())), 1)

    @override_settings(TEST_ADDONS=("weblate.addons.cleanup.CleanupAddon"))
    def test_invalid(self) -> None:
        loader = ClassLoader("TEST_ADDONS", construct=False, base_class=BaseAddon)  # noqa: F841
        errors = check_class_loader(app_configs=None, databases=None)
        self.assertEqual(len(errors), 1)

    @override_settings(TEST_ADDONS=("weblate.addons.not_found",))
    def test_not_found(self) -> None:
        loader = ClassLoader("TEST_ADDONS", construct=False, base_class=BaseAddon)  # noqa: F841
        errors = check_class_loader(app_configs=None, databases=None)
        self.assertEqual(len(errors), 1)
        self.assertIn("does not define a 'not_found' class", errors[0].msg)
