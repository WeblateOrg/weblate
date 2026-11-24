# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app integration."""

from __future__ import annotations

from base64 import b64decode
from typing import cast
from unittest.mock import AsyncMock, patch

import jwt as pyjwt
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from weblate.utils.tests import http_mock
from weblate.vcs.github import (
    JWT_MAX_LIFETIME,
    GitHubAppCredentials,
    exchange_github_app_manifest_code,
    exchange_github_user_code,
    generate_jwt,
    get_app_repositories,
    get_app_repository,
    get_github_api_base,
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_settings,
    get_github_git_auth_environment,
    get_user_admin_installation,
    github_app_is_configured,
    user_can_administer_org_installation,
    validate_private_key,
    verify_webhook_signature,
)
from weblate.vcs.tests.utils import generate_private_key, sign_webhook_payload


class TestGithubAppHookUtils(TestCase):
    def test_validate_private_key(self) -> None:
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

    def test_generate_jwt(self) -> None:
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

    def test_get_github_api_base(self) -> None:
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

    def test_create_app_credentials(self) -> None:
        self.create_app_credentials(hostname="github.example.com")
        config = get_github_app_settings()
        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.app_id, "12345")
        self.assertEqual(config.app_slug, "weblate-app")
        self.assertEqual(config.hostname, "github.example.com")
        self.assertTrue(github_app_is_configured())

    def test_github_app_install_url(self) -> None:
        self.create_app_credentials(hostname="github.com")
        self.assertEqual(
            get_github_app_install_url("signed-state"),
            "https://github.com/apps/weblate-app/installations/select_target?state=signed-state",
        )

    def test_github_app_multiple_hosts_require_explicit_selection(self) -> None:
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
            cast(
                "GitHubAppCredentials", get_github_app_settings("github.example.com")
            ).app_slug,
            "weblate-enterprise-app",
        )
        self.assertEqual(
            cast(
                "GitHubAppCredentials", get_github_app_settings("api.github.com")
            ).hostname,
            "github.com",
        )
        self.assertEqual(
            get_github_app_install_url("signed-state", "github.example.com"),
            "https://github.example.com/github-apps/weblate-enterprise-app/installations/select_target?state=signed-state",
        )

    def test_git_auth_environment(self) -> None:
        environment = get_github_git_auth_environment("x-access-token", "ghs_test")
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(environment["GIT_CONFIG_KEY_0"], "http.extraHeader")
        # proactiveAuth must NOT be set: it causes Git to skip the
        # unauthenticated probe and prompt for credentials instead of using
        # the extraHeader we provided.
        self.assertFalse(
            any("proactiveAuth" in value for value in environment.values())
        )
        header = environment["GIT_CONFIG_VALUE_0"]
        self.assertEqual(
            b64decode(header.removeprefix("Authorization: Basic ")).decode("utf-8"),
            "x-access-token:ghs_test",
        )

    def test_verify_webhook_signature(self) -> None:
        payload = b'{"action": "push"}'
        self.assertTrue(
            verify_webhook_signature(payload, sign_webhook_payload(payload, "s"), "s")
        )

        self.assertFalse(
            verify_webhook_signature(b'{"action": "push"}', "sha256=invalid", "s")
        )

        self.assertFalse(verify_webhook_signature(b"t", "invalid", "s"))

        self.assertFalse(verify_webhook_signature(b"t", "", "s"))

    def test_verify_webhook_signature_non_ascii(self) -> None:
        for signature in ("sha256=é", "sha256=" + "é" * 64, "sha256=🔒"):
            with self.subTest(signature=signature):
                self.assertFalse(verify_webhook_signature(b"t", signature, "s"))

    def test_github_app_is_configured(self) -> None:
        self.assertEqual(get_github_app_configurations(), {})
        self.assertFalse(github_app_is_configured())

        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="fromdb",
            app_slug="db-app",
            private_key=generate_private_key(),
            webhook_secret="db-secret",
        )

        configs = get_github_app_configurations()
        self.assertEqual(configs["github.com"].app_id, "fromdb")
        self.assertEqual(configs["github.com"].webhook_secret, "db-secret")
        self.assertTrue(github_app_is_configured())


@override_settings(
    VCS_RESTRICT_PRIVATE=True,
    VCS_ALLOW_HOSTS=[],
    VCS_PRIVATE_ALLOWLIST=[],
)
class GitHubAppOutboundTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(
            patch("weblate.utils.requests.get_environment_proxy", return_value=None)
        )
        self.resolve = self.enterContext(
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("93.184.216.34", 443))],
            )
        )
        self.enterContext(
            patch(
                "weblate.vcs.github.get_installation_token",
                new=AsyncMock(return_value="installation-token"),
            )
        )
        self.config = GitHubAppCredentials(hostname="github.example.com")

    @http_mock.activate
    async def test_private_registration_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            await exchange_github_app_manifest_code("code", "127.0.0.1")
        self.assertEqual(len(http_mock.calls), 0)

    @http_mock.activate
    async def test_private_oauth_rejected(self) -> None:
        self.resolve.return_value = [(0, 0, 0, "", ("10.0.0.1", 443))]
        with self.assertRaises(ValidationError):
            await exchange_github_user_code(self.config, "code")
        self.assertEqual(len(http_mock.calls), 0)

    @http_mock.activate
    async def test_public_repository_redirect_pins_each_request(self) -> None:
        old_url = "https://github.example.com/api/v3/repos/owner/old"
        new_url = "https://github.example.com/api/v3/repos/owner/new"
        http_mock.register(
            "GET", old_url, status_code=301, headers={"Location": new_url}
        )
        http_mock.register("GET", new_url, json={"full_name": "owner/new"})

        repository = await get_app_repository(
            "1", "key", "2", self.config.hostname, "owner/old"
        )

        self.assertEqual(repository, {"full_name": "owner/new"})
        self.assertEqual(self.resolve.call_count, 2)
        self.assertEqual(len(http_mock.calls), 2)
        for request_call in http_mock.calls:
            self.assertEqual(
                http_mock.get_transport_url(request_call.request).host, "93.184.216.34"
            )

    @http_mock.activate
    async def test_private_redirect_rejected(self) -> None:
        http_mock.register(
            "POST",
            "https://github.example.com/api/v3/app-manifests/code/conversions",
            status_code=302,
            headers={"Location": "https://127.0.0.1/internal"},
        )
        with self.assertRaises(ValidationError):
            await exchange_github_app_manifest_code("code", self.config.hostname)
        self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    async def test_private_pagination_rejected(self) -> None:
        for path, function, args, payload in (
            (
                "installation/repositories",
                get_app_repositories,
                ("1", "key", "2", self.config.hostname),
                {"repositories": []},
            ),
            (
                "user/installations",
                get_user_admin_installation,
                (self.config, "user-token", "2"),
                {"installations": []},
            ),
            (
                "orgs/owner/installations",
                user_can_administer_org_installation,
                (self.config, "user-token", "owner", "2"),
                {"installations": []},
            ),
        ):
            with self.subTest(path=path):
                http_mock.reset()
                http_mock.register(
                    "GET",
                    f"https://github.example.com/api/v3/{path}?per_page=100",
                    json=payload,
                    headers={"Link": '<https://127.0.0.1/internal>; rel="next"'},
                )
                with self.assertRaises(ValidationError):
                    await function(*args)
                self.assertEqual(len(http_mock.calls), 1)

    @http_mock.activate
    async def test_private_host_exemptions(self) -> None:
        self.resolve.return_value = [(0, 0, 0, "", ("10.0.0.1", 443))]
        http_mock.register(
            "POST",
            "https://github.example.com/login/oauth/access_token",
            json={"access_token": "user-token"},
        )
        for configuration in (
            {"VCS_RESTRICT_PRIVATE": False},
            {"VCS_ALLOW_HOSTS": ["github.example.com"]},
            {"VCS_PRIVATE_ALLOWLIST": [".example.com"]},
        ):
            with (
                self.subTest(configuration=configuration),
                override_settings(**configuration),
            ):
                self.assertEqual(
                    await exchange_github_user_code(self.config, "code"), "user-token"
                )
        self.assertEqual(len(http_mock.calls), 3)

    @http_mock.activate
    @override_settings(VCS_PRIVATE_ALLOWLIST=["github.example.com"])
    async def test_exemption_does_not_allow_private_redirect(self) -> None:
        http_mock.register(
            "POST",
            "https://github.example.com/login/oauth/access_token",
            status_code=302,
            headers={"Location": "https://127.0.0.1/internal"},
        )
        with self.assertRaises(ValidationError):
            await exchange_github_user_code(self.config, "code")
        self.assertEqual(len(http_mock.calls), 1)
