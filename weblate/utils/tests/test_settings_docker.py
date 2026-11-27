# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from pathlib import Path
from runpy import run_module
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DockerTranslationMaxUnitsTest(SimpleTestCase):
    def test_default_and_override(self) -> None:
        environment = {
            "WEBLATE_SITE_DOMAIN": "example.com",
            "WEBLATE_DATABASES": "0",
            "WEBLATE_SECRET_KEY": "environment-secret",
        }
        for overrides, limit in (
            ({}, 200_000),
            ({"WEBLATE_TRANSLATION_MAX_UNITS": "150000"}, 150_000),
        ):
            with (
                self.subTest(overrides=overrides),
                patch.dict(os.environ, environment | overrides, clear=True),
            ):
                configuration = run_module("weblate.settings_docker")
            self.assertEqual(configuration["TRANSLATION_MAX_UNITS"], limit)


class DockerEmailValidationExpiryTest(SimpleTestCase):
    def test_default_fallback_and_precedence(self) -> None:
        native = "WEBLATE_SOCIAL_AUTH_EMAIL_VALIDATION_EXPIRED_THRESHOLD"
        legacy = "WEBLATE_AUTH_TOKEN_VALID"
        environment = {
            "WEBLATE_SITE_DOMAIN": "example.com",
            "WEBLATE_DATABASES": "0",
            "WEBLATE_SECRET_KEY": "environment-secret",
        }
        for overrides, lifetime in (
            ({}, 172800),
            ({legacy: "7200"}, 7200),
            ({native: "3600"}, 3600),
            ({native: "0", legacy: "7200"}, 0),
        ):
            with (
                self.subTest(overrides=overrides),
                patch.dict(os.environ, environment | overrides, clear=True),
            ):
                configuration = run_module("weblate.settings_docker")
                self.assertEqual(
                    configuration["SOCIAL_AUTH_EMAIL_VALIDATION_EXPIRED_THRESHOLD"],
                    lifetime,
                )


class DockerSecretKeyTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "WEBLATE_SITE_DOMAIN": "example.com",
                    "WEBLATE_DATABASES": "0",
                },
                clear=True,
            )
        )

    def test_environment(self) -> None:
        os.environ["WEBLATE_SECRET_KEY"] = "environment-secret"
        with patch.object(Path, "read_text", autospec=True) as read_secret:
            configuration = run_module("weblate.settings_docker")
        self.assertEqual(configuration["SECRET_KEY"], "environment-secret")
        read_secret.assert_not_called()

    def test_file_precedence(self) -> None:
        os.environ["WEBLATE_SECRET_KEY_FILE"] = "/run/secrets/weblate_secret_key"
        for overrides in ({}, {"WEBLATE_SECRET_KEY": "environment-secret"}):
            with (
                self.subTest(overrides=overrides),
                patch.dict(os.environ, overrides),
                patch.object(
                    Path, "read_text", autospec=True, return_value="file-secret\n"
                ) as read_secret,
            ):
                configuration = run_module("weblate.settings_docker")
                self.assertEqual(configuration["SECRET_KEY"], "file-secret\n")
                read_secret.assert_called_once_with(
                    Path("/run/secrets/weblate_secret_key"), encoding="utf-8"
                )

    def test_default_file(self) -> None:
        for overrides in ({}, {"WEBLATE_SECRET_KEY": ""}):
            with (
                self.subTest(overrides=overrides),
                patch.dict(os.environ, overrides),
                patch.object(
                    Path, "read_text", autospec=True, return_value="default-secret\n"
                ) as read_secret,
            ):
                configuration = run_module("weblate.settings_docker")
                self.assertEqual(configuration["SECRET_KEY"], "default-secret\n")
                read_secret.assert_called_once_with(
                    Path("/app/data/secret"), encoding="utf-8"
                )

    def test_empty_file(self) -> None:
        os.environ["WEBLATE_SECRET_KEY"] = "environment-secret"
        os.environ["WEBLATE_SECRET_KEY_FILE"] = "/run/secrets/weblate_secret_key"
        with patch.object(
            Path, "read_text", autospec=True, side_effect=["", "default-secret"]
        ) as read_secret:
            configuration = run_module("weblate.settings_docker")
        self.assertEqual(configuration["SECRET_KEY"], "default-secret")
        self.assertEqual(read_secret.call_count, 2)
        read_secret.assert_any_call(
            Path("/run/secrets/weblate_secret_key"), encoding="utf-8"
        )
        read_secret.assert_called_with(Path("/app/data/secret"), encoding="utf-8")

    def test_unreadable_file(self) -> None:
        os.environ["WEBLATE_SECRET_KEY"] = "environment-secret"
        os.environ["WEBLATE_SECRET_KEY_FILE"] = "/run/secrets/weblate_secret_key"
        with (
            patch.object(
                Path, "read_text", autospec=True, side_effect=PermissionError
            ) as read_secret,
            self.assertRaisesMessage(
                ImproperlyConfigured,
                "Failed to open /run/secrets/weblate_secret_key as specified by WEBLATE_SECRET_KEY_FILE",
            ),
        ):
            run_module("weblate.settings_docker")
        read_secret.assert_called_once_with(
            Path("/run/secrets/weblate_secret_key"), encoding="utf-8"
        )


class DockerMediaStorageTest(SimpleTestCase):
    @patch.dict(
        os.environ,
        {
            "WEBLATE_SITE_DOMAIN": "example.com",
            "WEBLATE_DATABASES": "0",
            "WEBLATE_SECRET_KEY": "environment-secret",
            "WEBLATE_MEDIA_STORAGE_BACKEND": "storages.backends.s3.S3Storage",
            "WEBLATE_MEDIA_STORAGE_OPTIONS": '{"bucket_name": "weblate-media"}',
        },
        clear=True,
    )
    def test_environment(self) -> None:
        configuration = run_module("weblate.settings_docker")
        self.assertEqual(
            configuration["STORAGES"]["default"],
            {
                "BACKEND": "storages.backends.s3.S3Storage",
                "OPTIONS": {"bucket_name": "weblate-media"},
            },
        )

    @patch.dict(
        os.environ,
        {
            "WEBLATE_SITE_DOMAIN": "example.com",
            "WEBLATE_DATABASES": "0",
            "WEBLATE_SECRET_KEY": "environment-secret",
            "WEBLATE_FONTS_STORAGE_BACKEND": "storages.backends.s3.S3Storage",
            "WEBLATE_FONTS_STORAGE_OPTIONS": '{"bucket_name": "weblate-fonts"}',
        },
        clear=True,
    )
    def test_fonts_environment(self) -> None:
        configuration = run_module("weblate.settings_docker")
        self.assertEqual(
            configuration["STORAGES"]["fonts"],
            {
                "BACKEND": "storages.backends.s3.S3Storage",
                "OPTIONS": {"bucket_name": "weblate-fonts"},
            },
        )
