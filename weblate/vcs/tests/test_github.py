# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app integration."""

from __future__ import annotations

from base64 import b64decode

import jwt as pyjwt
from django.test import TestCase

from weblate.vcs.github import (
    JWT_MAX_LIFETIME,
    GitHubAppCredentials,
    generate_jwt,
    get_github_api_base,
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_settings,
    get_github_git_auth_args,
    github_app_is_configured,
    validate_private_key,
    verify_webhook_signature,
)
from weblate.vcs.tests.utils import generate_private_key, sign_webhook_payload


class TestGithubAppHookUtils(TestCase):
    def test_validate_private_key(self):
        private_key = generate_private_key()

        result = validate_private_key(private_key)
        self.assertTrue(result.startswith("-----BEGIN"))

        result = validate_private_key(f"  {private_key}  ")
        self.assertTrue(result.startswith("-----BEGIN"))

        with self.assertRaises(ValueError):
            validate_private_key("/etc/shadow")

        with self.assertRaises(ValueError):
            validate_private_key(
                "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"
            )

    def test_generate_jwt(self):
        private_key = generate_private_key()

        token = generate_jwt("12345", private_key)
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(decoded["iss"], "12345")
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)
        # iat is now-60, exp is now+JWT_MAX_LIFETIME → spread = 60 + JWT_MAX_LIFETIME
        self.assertEqual(decoded["exp"] - decoded["iat"], 60 + JWT_MAX_LIFETIME)
        # Must stay within GitHub's 10-minute hard cap
        self.assertLessEqual(JWT_MAX_LIFETIME, 10 * 60)

        header = pyjwt.get_unverified_header(token)
        self.assertEqual(header["alg"], "RS256")

    def test_get_github_api_base(self):
        self.assertEqual(get_github_api_base("github.com"), "https://api.github.com")

        self.assertEqual(
            get_github_api_base("github.example.com"),
            "https://github.example.com/api/v3",
        )

    def create_app_credentials(self, hostname: str = "github.com", **overrides):
        """Create a GitHubAppCredentials row for tests."""
        defaults = {
            "app_id": "12345",
            "app_slug": "weblate-app",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
            "webhook_secret": "secret",
        }
        defaults.update(overrides)
        return GitHubAppCredentials.objects.create(hostname=hostname, **defaults)

    def test_create_app_credentials(self):
        self.create_app_credentials(hostname="github.example.com")
        config = get_github_app_settings()
        self.assertIsNotNone(config)
        self.assertEqual(config.app_id, "12345")
        self.assertEqual(config.app_slug, "weblate-app")
        self.assertEqual(config.hostname, "github.example.com")
        self.assertTrue(github_app_is_configured())

    def test_github_app_install_url(self):
        self.create_app_credentials(hostname="github.com")
        self.assertEqual(
            get_github_app_install_url("signed-state"),
            "https://github.com/apps/weblate-app/installations/select_target?state=signed-state",
        )

    def test_github_app_multiple_hosts_require_explicit_selection(self):
        # ``api.github.com`` is normalized to ``github.com`` on save.
        self.create_app_credentials(hostname="api.github.com")
        self.create_app_credentials(
            hostname="github.example.com",
            app_id="67890",
            app_slug="weblate-enterprise-app",
            webhook_secret="enterprise-secret",
        )
        self.assertIsNone(get_github_app_settings())
        self.assertEqual(
            get_github_app_configurations()["github.com"].app_slug,
            "weblate-app",
        )
        self.assertEqual(
            get_github_app_settings("github.example.com").app_slug,
            "weblate-enterprise-app",
        )
        self.assertEqual(
            get_github_app_settings("api.github.com").hostname,
            "github.com",
        )
        self.assertEqual(
            get_github_app_install_url("signed-state", "github.example.com"),
            "https://github.example.com/github-apps/weblate-enterprise-app/installations/select_target?state=signed-state",
        )

    def test_git_auth_args(self):
        args = list(get_github_git_auth_args("x-access-token", "ghs_test"))
        self.assertEqual(args[0], "-c")
        self.assertTrue(args[1].startswith("http.extraHeader=Authorization: Basic "))
        # proactiveAuth must NOT be set: it causes Git to skip the
        # unauthenticated probe and prompt for credentials instead of using
        # the extraHeader we provided.
        self.assertFalse(any("proactiveAuth" in arg for arg in args))
        header = args[1].removeprefix("http.extraHeader=")
        self.assertEqual(
            b64decode(header.removeprefix("Authorization: Basic ")).decode("utf-8"),
            "x-access-token:ghs_test",
        )

    def test_verify_webhook_signature(self):
        payload = b'{"action": "push"}'
        self.assertTrue(
            verify_webhook_signature(payload, sign_webhook_payload(payload, "s"), "s")
        )

        self.assertFalse(
            verify_webhook_signature(b'{"action": "push"}', "sha256=invalid", "s")
        )

        self.assertFalse(verify_webhook_signature(b"t", "invalid", "s"))

        self.assertFalse(verify_webhook_signature(b"t", "", "s"))

    def test_github_app_is_configured(self):
        self.assertEqual(get_github_app_configurations(), {})
        self.assertFalse(github_app_is_configured())

        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="fromdb",
            app_slug="db-app",
            private_key="-----BEGIN RSA PRIVATE KEY-----\ndb\n-----END RSA PRIVATE KEY-----",
            webhook_secret="db-secret",
        )

        configs = get_github_app_configurations()
        self.assertEqual(configs["github.com"].app_id, "fromdb")
        self.assertEqual(configs["github.com"].webhook_secret, "db-secret")
        self.assertTrue(github_app_is_configured())
