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
            'Error importing class unittest in TEST: .*"' "(not enough|need more than)",
        ):
            load_class("unittest", "TEST")

    def test_invalid_module(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            'weblate.trans.tests.missing in TEST: "' "No module named .*missing[\"']",
        ):
            load_class("weblate.trans.tests.missing.Foo", "TEST")

    def test_invalid_class(self):
        with self.assertRaisesRegex(
            ImproperlyConfigured,
            '"weblate.utils.tests.test_classloader"' ' does not define a "Foo" class',
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
