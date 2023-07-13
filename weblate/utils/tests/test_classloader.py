# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from django.core.exceptions import ImproperlyConfigured
from django.test.utils import override_settings

from weblate.utils.classloader import ClassLoader, load_class


class LoadClassTest(TestCase):
    def test_correct(self):
        cls = load_class("unittest.TestCase", "TEST")
        self.assertEqual(cls, TestCase)

    def test_invalid_name(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "Error importing class 'unittest' in TEST: (not enough|need more than)",
        ):
            load_class("unittest", "TEST")

    def test_invalid_module(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "'weblate.trans.tests.missing' in TEST: No module named .*missing",
        ):
            load_class("weblate.trans.tests.missing.Foo", "TEST")

    def test_invalid_class(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "'weblate.utils.tests.test_classloader' does not define a 'Foo' class",
        ):
            load_class("weblate.utils.tests.test_classloader.Foo", "TEST")


class ClassLoaderTestCase(TestCase):
    @override_settings(TEST_SERVICES=("weblate.addons.cleanup.CleanupAddon",))
    def test_load(self):
        loader = ClassLoader("TEST_SERVICES", construct=False)
        loader.load_data()
        self.assertEqual(len(list(loader.keys())), 1)

    @override_settings(TEST_SERVICES=("weblate.addons.cleanup.CleanupAddon"))
    def test_invalid(self):
        loader = ClassLoader("TEST_SERVICES", construct=False)
        with self.assertRaisesRegex(
            ImproperlyConfigured, "Setting TEST_SERVICES must be list or tuple!"
        ):
            loader.load_data()

    @override_settings(TEST_SERVICES=None)
    def test_none(self):
        loader = ClassLoader("TEST_SERVICES", construct=False)
        loader.load_data()
        self.assertEqual(len(list(loader.keys())), 0)
