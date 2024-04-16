# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.test import SimpleTestCase

from weblate.utils.environment import (
    get_env_bool,
    get_env_credentials,
    get_env_int,
    get_env_list,
    get_env_map,
    get_env_ratelimit,
    modify_env_list,
)


class EnvTest(SimpleTestCase):
    def test_list(self) -> None:
        os.environ["TEST_DATA"] = "foo,bar,baz"
        self.assertEqual(get_env_list("TEST_DATA"), ["foo", "bar", "baz"])
        os.environ["TEST_DATA"] = "foo"
        self.assertEqual(get_env_list("TEST_DATA"), ["foo"])
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_list("TEST_DATA"), [])
        self.assertEqual(get_env_list("TEST_DATA", ["x"]), ["x"])

    def test_map(self) -> None:
        os.environ["TEST_DATA"] = "foo:bar,baz:bag"
        self.assertEqual(get_env_map("TEST_DATA"), {"foo": "bar", "baz": "bag"})
        os.environ["TEST_DATA"] = "foo:bar"
        self.assertEqual(get_env_map("TEST_DATA"), {"foo": "bar"})
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_map("TEST_DATA"), {})
        self.assertEqual(get_env_map("TEST_DATA", {"x": "y"}), {"x": "y"})

    def test_bool(self) -> None:
        os.environ["TEST_DATA"] = "1"
        self.assertTrue(get_env_bool("TEST_DATA"))
        os.environ["TEST_DATA"] = "True"
        self.assertTrue(get_env_bool("TEST_DATA"))
        os.environ["TEST_DATA"] = "true"
        self.assertTrue(get_env_bool("TEST_DATA"))
        os.environ["TEST_DATA"] = "Yes"
        self.assertTrue(get_env_bool("TEST_DATA"))
        os.environ["TEST_DATA"] = "no"
        self.assertFalse(get_env_bool("TEST_DATA"))
        os.environ["TEST_DATA"] = "0"
        self.assertFalse(get_env_bool("TEST_DATA"))
        del os.environ["TEST_DATA"]
        self.assertFalse(get_env_bool("TEST_DATA"))

    def test_int(self) -> None:
        os.environ["TEST_DATA"] = "1"
        self.assertEqual(get_env_int("TEST_DATA"), 1)
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_int("TEST_DATA"), 0)

    def test_modify_list(self) -> None:
        os.environ["WEBLATE_ADD_TEST"] = "foo,bar"
        os.environ["WEBLATE_REMOVE_TEST"] = "baz,bag"
        setting = ["baz", "bag", "aaa"]
        modify_env_list(setting, "TEST")
        self.assertEqual(setting, ["foo", "bar", "aaa"])
        del os.environ["WEBLATE_ADD_TEST"]
        del os.environ["WEBLATE_REMOVE_TEST"]

    def test_get_env_credentials(self) -> None:
        os.environ["WEBLATE_TEST_USERNAME"] = "user"
        os.environ["WEBLATE_TEST_TOKEN"] = "token"
        os.environ["WEBLATE_TEST_ORGANIZATION"] = "organization"
        with self.assertRaises(ValueError):
            get_env_credentials("TEST")

        os.environ["WEBLATE_TEST_HOST"] = "host"
        self.assertEqual(
            get_env_credentials("TEST"),
            {
                "host": {
                    "username": "user",
                    "token": "token",
                    "organization": "organization",
                }
            },
        )

        del os.environ["WEBLATE_TEST_ORGANIZATION"]

        self.assertEqual(
            get_env_credentials("TEST"),
            {"host": {"username": "user", "token": "token"}},
        )

        del os.environ["WEBLATE_TEST_USERNAME"]
        del os.environ["WEBLATE_TEST_TOKEN"]
        del os.environ["WEBLATE_TEST_HOST"]

        os.environ["WEBLATE_TEST_CREDENTIALS"] = "{invalid-syntax}"
        with self.assertRaises(ValueError):
            get_env_credentials("TEST")

        os.environ["WEBLATE_TEST_CREDENTIALS"] = (
            '{"host": {"username": "user", "token": "token"}}'
        )
        self.assertEqual(
            get_env_credentials("TEST"),
            {"host": {"username": "user", "token": "token"}},
        )

        del os.environ["WEBLATE_TEST_CREDENTIALS"]

    def test_get_env_ratelimit(self) -> None:
        os.environ["RATELIMIT_ANON"] = "1/hour"
        self.assertEqual(
            get_env_ratelimit("RATELIMIT_ANON", ""),
            "1/hour",
        )
        os.environ["RATELIMIT_ANON"] = "1"
        with self.assertRaises(ValueError):
            get_env_ratelimit("RATELIMIT_ANON", "")
        del os.environ["RATELIMIT_ANON"]
