# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from django.core.exceptions import ImproperlyConfigured
from django.test.utils import override_settings

from weblate.addons.base import BaseAddon
from weblate.utils.classloader import ClassLoader, load_class


class LoadClassTest(TestCase):
    def test_correct(self) -> None:
        cls = load_class("unittest.TestCase", "TEST")
        self.assertEqual(cls, TestCase)

    def test_invalid_name(self) -> None:
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "Error importing class 'unittest' in TEST: (not enough|need more than)",
        ):
            load_class("unittest", "TEST")

    def test_invalid_module(self) -> None:
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "'weblate.trans.tests.missing' in TEST: No module named .*missing",
        ):
            load_class("weblate.trans.tests.missing.Foo", "TEST")

    def test_invalid_class(self) -> None:
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            "'weblate.utils.tests.test_classloader' does not define a 'Foo' class",
        ):
            load_class("weblate.utils.tests.test_classloader.Foo", "TEST")


class ClassLoaderTestCase(TestCase):
    @override_settings(TEST_SERVICES=("weblate.addons.cleanup.CleanupAddon",))
    def test_load(self) -> None:
        loader = ClassLoader("TEST_SERVICES", construct=False, base_class=BaseAddon)
        loader.load_data()
        self.assertEqual(len(list(loader.keys())), 1)

    @override_settings(TEST_SERVICES=("weblate.addons.cleanup.CleanupAddon"))
    def test_invalid(self) -> None:
        loader = ClassLoader("TEST_SERVICES", construct=False, base_class=BaseAddon)
        with self.assertRaisesRegex(
            ImproperlyConfigured, "Setting TEST_SERVICES must be list or tuple!"
        ):
            loader.load_data()

    @override_settings(TEST_SERVICES=("weblate.addons.not_found",))
    def test_not_found(self) -> None:
        loader = ClassLoader("TEST_SERVICES", construct=False, base_class=BaseAddon)
        with self.assertRaisesRegex(
            ImproperlyConfigured, "does not define a 'not_found' class"
        ):
            loader.load_data()

    @override_settings(TEST_SERVICES=("weblate.addons.cleanup",))
    def test_module(self) -> None:
        loader = ClassLoader("TEST_SERVICES", construct=False, base_class=BaseAddon)
        with self.assertRaisesRegex(
            ImproperlyConfigured, "Setting TEST_SERVICES must be a BaseAddon subclass"
        ):
            loader.load_data()

    @override_settings(TEST_SERVICES=("weblate.accounts.auth.WeblateUserBackend",))
    def test_other_class(self) -> None:
        loader = ClassLoader("TEST_SERVICES", construct=False, base_class=BaseAddon)
        with self.assertRaisesRegex(
            ImproperlyConfigured, "Setting TEST_SERVICES must be a BaseAddon subclass"
        ):
            loader.load_data()

    @override_settings(TEST_SERVICES=None)
    def test_none(self) -> None:
        loader = ClassLoader("TEST_SERVICES", construct=False, base_class=BaseAddon)
        loader.load_data()
        self.assertEqual(len(list(loader.keys())), 0)
