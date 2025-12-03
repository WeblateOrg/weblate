# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from weblate.utils.environment import (
    get_env_bool,
    get_env_credentials,
    get_env_int,
    get_env_int_or_none,
    get_env_list,
    get_env_list_or_none,
    get_env_map,
    get_env_map_or_none,
    get_env_ratelimit,
    get_env_redis_url,
    get_env_str,
    get_saml_idp,
    modify_env_list,
)
from weblate.utils.files import remove_tree
from weblate.utils.unittest import tempdir_setting


class EnvTest(SimpleTestCase):
    def test_str(self) -> None:
        os.environ["TEST_DATA"] = "foo"
        self.assertEqual(get_env_str("TEST_DATA"), "foo")
        self.assertEqual(get_env_str("TEST_DATA", default="bar", required=True), "foo")
        os.environ["TEST_DATA"] = ""
        self.assertEqual(get_env_str("TEST_DATA"), "")
        self.assertEqual(get_env_str("TEST_DATA", default="bar"), "")
        del os.environ["TEST_DATA"]
        self.assertIsNone(get_env_str("TEST_DATA"))
        self.assertEqual(get_env_str("TEST_DATA", default="bar"), "bar")
        self.assertEqual(get_env_str("TEST_DATA", default="bar", required=True), "bar")
        with self.assertRaises(ImproperlyConfigured):
            get_env_str("TEST_DATA", required=True)

    @tempdir_setting("DATA_DIR")
    def test_str_files(self) -> None:
        target = os.path.join(settings.DATA_DIR, "test")
        os.makedirs(target)
        filepath = Path(os.path.join(target, "file"))
        filepath.write_text("bar", encoding="utf-8")
        os.environ["TEST_DATA_FILE"] = str(filepath)
        self.assertEqual(get_env_str("TEST_DATA"), "bar")
        self.assertEqual(get_env_str("TEST_DATA", required=True), "bar")
        self.assertEqual(get_env_str("TEST_DATA", default="baz", required=True), "bar")
        os.environ["TEST_DATA"] = "foo"
        self.assertEqual(get_env_str("TEST_DATA"), "bar")
        self.assertEqual(get_env_str("TEST_DATA"), "bar")
        self.assertEqual(get_env_str("TEST_DATA", required=True), "bar")
        self.assertEqual(get_env_str("TEST_DATA", default="baz", required=True), "bar")
        filepath.write_text("", encoding="utf-8")
        self.assertEqual(get_env_str("TEST_DATA"), "")
        del os.environ["TEST_DATA_FILE"]
        self.assertEqual(get_env_str("TEST_DATA"), "foo")
        self.assertEqual(get_env_str("TEST_DATA", required=True), "foo")
        self.assertEqual(get_env_str("TEST_DATA", default="baz", required=True), "foo")
        del os.environ["TEST_DATA"]
        self.assertIsNone(get_env_str("TEST_DATA"))
        remove_tree(target)

    @tempdir_setting("DATA_DIR")
    def test_str_fallback(self) -> None:
        target = os.path.join(settings.DATA_DIR, "test")
        os.makedirs(target)
        filepath = Path(os.path.join(target, "file"))
        filepath.write_text("baz", encoding="utf-8")

        os.environ["TEST_DATA"] = "foo"
        os.environ["TEST_DATA_FALLBACK"] = "bar"
        os.environ["TEST_DATA_FALLBACK_FILE"] = str(filepath)
        self.assertEqual(
            get_env_str("TEST_DATA", fallback_name="TEST_DATA_FALLBACK"), "foo"
        )
        self.assertEqual(
            get_env_str("TEST_DATA", required=True, fallback_name="TEST_DATA_FALLBACK"),
            "foo",
        )
        self.assertEqual(
            get_env_str(
                "TEST_DATA",
                default="foobar",
                required=True,
                fallback_name="TEST_DATA_FALLBACK",
            ),
            "foo",
        )
        del os.environ["TEST_DATA"]
        self.assertEqual(
            get_env_str("TEST_DATA", fallback_name="TEST_DATA_FALLBACK"), "baz"
        )
        self.assertEqual(
            get_env_str("TEST_DATA", required=True, fallback_name="TEST_DATA_FALLBACK"),
            "baz",
        )
        self.assertEqual(
            get_env_str(
                "TEST_DATA",
                default="foobar",
                required=True,
                fallback_name="TEST_DATA_FALLBACK",
            ),
            "baz",
        )
        del os.environ["TEST_DATA_FALLBACK_FILE"]
        self.assertEqual(
            get_env_str("TEST_DATA", fallback_name="TEST_DATA_FALLBACK"), "bar"
        )
        self.assertEqual(
            get_env_str("TEST_DATA", required=True, fallback_name="TEST_DATA_FALLBACK"),
            "bar",
        )
        self.assertEqual(
            get_env_str(
                "TEST_DATA",
                default="foobar",
                required=True,
                fallback_name="TEST_DATA_FALLBACK",
            ),
            "bar",
        )
        del os.environ["TEST_DATA_FALLBACK"]
        self.assertIsNone(get_env_str("TEST_DATA", fallback_name="TEST_DATA_FALLBACK"))
        self.assertEqual(
            get_env_str(
                "TEST_DATA", default="foobar", fallback_name="TEST_DATA_FALLBACK"
            ),
            "foobar",
        )
        remove_tree(target)

    def test_list(self) -> None:
        os.environ["TEST_DATA"] = "foo,bar,baz"
        self.assertEqual(get_env_list("TEST_DATA"), ["foo", "bar", "baz"])
        os.environ["TEST_DATA"] = "foo"
        self.assertEqual(get_env_list("TEST_DATA"), ["foo"])
        os.environ["TEST_DATA"] = ""
        self.assertEqual(get_env_list("TEST_DATA"), [""])
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_list("TEST_DATA"), [])
        self.assertEqual(get_env_list("TEST_DATA", ["x"]), ["x"])

    def test_list_or_none(self) -> None:
        os.environ["TEST_DATA"] = "foo,bar,baz"
        self.assertEqual(get_env_list_or_none("TEST_DATA"), ["foo", "bar", "baz"])
        os.environ["TEST_DATA"] = "foo"
        self.assertEqual(get_env_list_or_none("TEST_DATA"), ["foo"])
        os.environ["TEST_DATA"] = ""
        self.assertEqual(get_env_list_or_none("TEST_DATA"), [""])
        del os.environ["TEST_DATA"]
        self.assertIsNone(get_env_list_or_none("TEST_DATA"))

    def test_map(self) -> None:
        os.environ["TEST_DATA"] = "foo:bar,baz:bag"
        self.assertEqual(get_env_map("TEST_DATA"), {"foo": "bar", "baz": "bag"})
        os.environ["TEST_DATA"] = "foo:bar"
        self.assertEqual(get_env_map("TEST_DATA"), {"foo": "bar"})
        os.environ["TEST_DATA"] = ""
        self.assertEqual(get_env_map("TEST_DATA"), {})
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_map("TEST_DATA"), {})
        self.assertEqual(get_env_map("TEST_DATA", {"x": "y"}), {"x": "y"})

    def test_map_or_none(self) -> None:
        os.environ["TEST_DATA"] = "foo:bar,baz:bag"
        self.assertEqual(get_env_map_or_none("TEST_DATA"), {"foo": "bar", "baz": "bag"})
        os.environ["TEST_DATA"] = "foo:bar"
        self.assertEqual(get_env_map_or_none("TEST_DATA"), {"foo": "bar"})
        os.environ["TEST_DATA"] = ""
        self.assertEqual(get_env_map_or_none("TEST_DATA"), {})
        del os.environ["TEST_DATA"]
        self.assertIsNone(get_env_map_or_none("TEST_DATA"))

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
        os.environ["TEST_DATA"] = ""
        self.assertFalse(get_env_bool("TEST_DATA"))
        del os.environ["TEST_DATA"]
        self.assertFalse(get_env_bool("TEST_DATA"))

    def test_int(self) -> None:
        os.environ["TEST_DATA"] = "1"
        self.assertEqual(get_env_int("TEST_DATA"), 1)
        os.environ["TEST_DATA"] = ""
        with self.assertRaises(ImproperlyConfigured):
            get_env_int("TEST_DATA")
        del os.environ["TEST_DATA"]
        self.assertEqual(get_env_int("TEST_DATA"), 0)

    def test_int_or_none(self) -> None:
        os.environ["TEST_DATA"] = "1"
        self.assertEqual(get_env_int_or_none("TEST_DATA"), 1)
        os.environ["TEST_DATA"] = ""
        with self.assertRaises(ImproperlyConfigured):
            get_env_int_or_none("TEST_DATA")
        del os.environ["TEST_DATA"]
        self.assertIsNone(get_env_int_or_none("TEST_DATA"))

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
        with self.assertRaises(ImproperlyConfigured):
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
        with self.assertRaises(ImproperlyConfigured):
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
        with self.assertRaises(ImproperlyConfigured):
            get_env_ratelimit("RATELIMIT_ANON", "")
        del os.environ["RATELIMIT_ANON"]

    def test_redis_url(self) -> None:
        def cleanup() -> None:
            toremove = [name for name in os.environ if name.startswith("REDIS_")]
            for name in toremove:
                del os.environ[name]

        cleanup()
        try:
            self.assertEqual(get_env_redis_url(), "redis://cache:6379/1")

            os.environ["REDIS_TLS"] = "1"
            self.assertEqual(get_env_redis_url(), "rediss://cache:6379/1")

            os.environ["REDIS_PASSWORD"] = "pass:word"
            self.assertEqual(get_env_redis_url(), "rediss://:pass%3Aword@cache:6379/1")

            os.environ["REDIS_USER"] = "user@example.com"
            self.assertEqual(
                get_env_redis_url(),
                "rediss://user%40example.com:pass%3Aword@cache:6379/1",
            )

            del os.environ["REDIS_PASSWORD"]
            self.assertEqual(
                get_env_redis_url(), "rediss://user%40example.com@cache:6379/1"
            )

            os.environ["REDIS_PORT"] = "1234"
            self.assertEqual(
                get_env_redis_url(), "rediss://user%40example.com@cache:1234/1"
            )

            os.environ["REDIS_PORT"] = "invalid"
            with self.assertRaises(ImproperlyConfigured):
                get_env_redis_url()
            del os.environ["REDIS_PORT"]

            os.environ["REDIS_HOST"] = ""
            with self.assertRaises(ImproperlyConfigured):
                get_env_redis_url()
        finally:
            cleanup()

    def test_saml(self) -> None:
        def cleanup() -> None:
            toremove = [name for name in os.environ if name.startswith("WEBLATE_SAML_")]
            for name in toremove:
                del os.environ[name]

        cleanup()
        try:
            self.assertIsNone(get_saml_idp())
            os.environ["WEBLATE_SAML_IDP_ENTITY_ID"] = "https://example.com/entity"
            self.assertEqual(
                get_saml_idp(),
                {
                    "entity_id": "https://example.com/entity",
                    "url": None,
                    "x509cert": None,
                },
            )
            os.environ["WEBLATE_SAML_IDP_URL"] = "https://example.com/idp"
            self.assertEqual(
                get_saml_idp(),
                {
                    "entity_id": "https://example.com/entity",
                    "url": "https://example.com/idp",
                    "x509cert": None,
                },
            )
            os.environ["WEBLATE_SAML_IDP_X509CERT"] = "--CERT--"
            self.assertEqual(
                get_saml_idp(),
                {
                    "entity_id": "https://example.com/entity",
                    "url": "https://example.com/idp",
                    "x509cert": "--CERT--",
                },
            )
            os.environ["WEBLATE_SAML_ID_ATTR_FULL_NAME"] = "fullname"
            self.assertEqual(
                get_saml_idp(),
                {
                    "entity_id": "https://example.com/entity",
                    "url": "https://example.com/idp",
                    "x509cert": "--CERT--",
                    "attr_full_name": "fullname",
                },
            )
        finally:
            cleanup()
