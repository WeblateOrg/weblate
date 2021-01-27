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

from django.test import SimpleTestCase

from weblate.utils.environment import (
    get_env_bool,
    get_env_int,
    get_env_list,
    get_env_map,
    modify_env_list,
)


class EnvTest(SimpleTestCase):
    def test_list(self):
        os.environ["TEST_DATA"] = "foo,bar,baz"
        self.assertEqual(get_env_list("TEST_DATA"), ["foo", "bar", "baz"])
        os.environ["TEST_DATA"] = "foo"
        self.assertEqual(get_env_list("TEST_DATA"), ["foo"])
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_list("TEST_DATA"), [])
        self.assertEqual(get_env_list("TEST_DATA", ["x"]), ["x"])

    def test_map(self):
        os.environ["TEST_DATA"] = "foo:bar,baz:bag"
        self.assertEqual(get_env_map("TEST_DATA"), {"foo": "bar", "baz": "bag"})
        os.environ["TEST_DATA"] = "foo:bar"
        self.assertEqual(get_env_map("TEST_DATA"), {"foo": "bar"})
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_map("TEST_DATA"), {})
        self.assertEqual(get_env_map("TEST_DATA", {"x": "y"}), {"x": "y"})

    def test_bool(self):
        os.environ["TEST_DATA"] = "1"
        self.assertEqual(get_env_bool("TEST_DATA"), True)
        os.environ["TEST_DATA"] = "True"
        self.assertEqual(get_env_bool("TEST_DATA"), True)
        os.environ["TEST_DATA"] = "true"
        self.assertEqual(get_env_bool("TEST_DATA"), True)
        os.environ["TEST_DATA"] = "Yes"
        self.assertEqual(get_env_bool("TEST_DATA"), True)
        os.environ["TEST_DATA"] = "no"
        self.assertEqual(get_env_bool("TEST_DATA"), False)
        os.environ["TEST_DATA"] = "0"
        self.assertEqual(get_env_bool("TEST_DATA"), False)
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_bool("TEST_DATA"), False)

    def test_int(self):
        os.environ["TEST_DATA"] = "1"
        self.assertEqual(get_env_int("TEST_DATA"), 1)
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_int("TEST_DATA"), 0)

    def test_modify_list(self):
        os.environ["WEBLATE_ADD_TEST"] = "foo,bar"
        os.environ["WEBLATE_REMOVE_TEST"] = "baz,bag"
        setting = ["baz", "bag", "aaa"]
        modify_env_list(setting, "TEST")
        self.assertEqual(setting, ["foo", "bar", "aaa"])
        del os.environ["WEBLATE_ADD_TEST"]
        del os.environ["WEBLATE_REMOVE_TEST"]
