# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app integration."""

from __future__ import annotations

import hashlib
import hmac
from base64 import b64decode
from unittest.mock import MagicMock, patch

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from weblate.trans.models import Component, Project
from weblate.vcs.base import RepositoryError
from weblate.vcs.git import GithubRepository
from weblate.vcs.github import (
    GITHUB_APP_MANIFEST_EVENTS,
    GITHUB_APP_MANIFEST_PERMISSIONS,
    JWT_MAX_LIFETIME,
    GitHubAppCredentials,
    GithubAppRepository,
    build_github_app_manifest,
    exchange_github_app_manifest_code,
    generate_jwt,
    get_github_api_base,
    get_github_app_configurations,
    get_github_app_install_url,
    get_github_app_manifest_new_url,
    get_github_app_settings,
    get_github_git_auth_args,
    get_installation_token,
    github_app_is_configured,
    validate_private_key,
    verify_webhook_signature,
)
from weblate.vcs.models import VCS_REGISTRY

SETTINGS_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----"
)


def create_app_credentials(hostname: str = "github.com", **overrides):
    """Create a GitHubAppCredentials row for tests."""
    defaults = {
        "app_id": "12345",
        "app_slug": "weblate-app",
        "private_key": SETTINGS_PRIVATE_KEY,
        "webhook_secret": "secret",
    }
    defaults.update(overrides)
    return GitHubAppCredentials.objects.create(hostname=hostname, **defaults)


def _generate_test_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


class GitHubAppTestBase(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.private_key = _generate_test_key()


class TestValidatePrivateKey(GitHubAppTestBase):
    def test_inline_key(self):
        result = validate_private_key(self.private_key)
        self.assertTrue(result.startswith("-----BEGIN"))

    def test_inline_key_with_whitespace(self):
        result = validate_private_key(f"  {self.private_key}  ")
        self.assertTrue(result.startswith("-----BEGIN"))

    def test_rejects_file_path(self):
        with self.assertRaises(ValueError):
            validate_private_key("/etc/shadow")

    def test_rejects_non_private_key_pem(self):
        with self.assertRaises(ValueError):
            validate_private_key(
                "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"
            )


class TestGenerateJWT(GitHubAppTestBase):
    def test_generate_jwt(self):
        token = generate_jwt("12345", self.private_key)
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        self.assertEqual(decoded["iss"], "12345")
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)
        # iat is now-60, exp is now+JWT_MAX_LIFETIME → spread = 60 + JWT_MAX_LIFETIME
        self.assertEqual(decoded["exp"] - decoded["iat"], 60 + JWT_MAX_LIFETIME)
        # Must stay within GitHub's 10-minute hard cap
        self.assertLessEqual(JWT_MAX_LIFETIME, 10 * 60)

    def test_jwt_uses_rs256(self):
        token = generate_jwt("12345", self.private_key)
        header = pyjwt.get_unverified_header(token)
        self.assertEqual(header["alg"], "RS256")


class TestGetGitHubApiBase(SimpleTestCase):
    def test_github_com(self):
        self.assertEqual(get_github_api_base("github.com"), "https://api.github.com")

    def test_github_enterprise(self):
        self.assertEqual(
            get_github_api_base("github.example.com"),
            "https://github.example.com/api/v3",
        )


class TestGitHubAppSettings(TestCase):
    def test_db_loaded(self):
        create_app_credentials(hostname="github.example.com")
        config = get_github_app_settings()
        self.assertIsNotNone(config)
        self.assertEqual(config.app_id, "12345")
        self.assertEqual(config.app_slug, "weblate-app")
        self.assertEqual(config.hostname, "github.example.com")
        self.assertTrue(github_app_is_configured())

    def test_install_url(self):
        create_app_credentials(hostname="github.com")
        self.assertEqual(
            get_github_app_install_url("signed-state"),
            "https://github.com/apps/weblate-app/installations/select_target?state=signed-state",
        )

    def test_multiple_hosts_require_explicit_selection(self):
        # ``api.github.com`` is normalized to ``github.com`` on save.
        create_app_credentials(hostname="api.github.com")
        create_app_credentials(
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


# Built at runtime so secret scanners don't flag the literal test URL.
_FAKE_USER = "bot"
_FAKE_TOKEN = "pat"
_FAKE_AUTH_GITHUB_URL = (
    f"https://{_FAKE_USER}:{_FAKE_TOKEN}@github.com/test-org/repo1.git"
)


class TestGithubAppRepositoryAuth(SimpleTestCase):
    def get_repo(self, repo_url: str) -> GithubAppRepository:
        component = Component(
            slug="test",
            name="Test",
            project=Project(name="Test", slug="test", pk=-1),
            source_language_id=1,
            branch="main",
            vcs="github-app",
            repo=repo_url,
            pk=-1,
        )
        return GithubAppRepository(".", branch="main", component=component, local=True)

    @patch("weblate.vcs.github.GitHubInstallation.objects.get_for_repo")
    def test_url_credentials_skip_github_app_git_auth(self, mock_get_for_repo):
        args = list(
            GithubAppRepository._get_auth_args(  # noqa: SLF001
                _FAKE_AUTH_GITHUB_URL
            )
        )

        self.assertEqual(args, ["-c", "http.proactiveAuth=auto"])
        mock_get_for_repo.assert_not_called()

    def test_get_remote_branch_validates_remote_url(self):
        with (
            patch.object(GithubAppRepository, "_popen") as mock_popen,
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(RepositoryError) as error,
        ):
            GithubAppRepository.get_remote_branch("https://private.example/repo.git")

        mock_popen.assert_not_called()
        self.assertIn("internal or non-public address", str(error.exception))

    def test_should_use_fork_is_always_false(self):
        repo = self.get_repo("https://github.com/test-org/repo1.git")
        self.assertFalse(repo.should_use_fork())
        self.assertFalse(repo.should_use_fork("custom-branch"))

    @patch.object(
        GithubAppRepository,
        "_resolve_github_app_token",
        return_value={
            "username": "x-access-token",
            "token": "ghs_test",
            "github_app": True,
        },
    )
    def test_url_credentials_are_not_tagged_as_github_app(self, mock_resolve):
        repo = self.get_repo(_FAKE_AUTH_GITHUB_URL)

        credentials = repo.get_credentials()

        # URL-embedded credentials win — App auth is only resolved via the
        # ``get_credentials_by_hostname`` path which the get_credentials
        # helper bypasses when the URL already carries auth.
        self.assertEqual(credentials["username"], _FAKE_USER)
        self.assertEqual(credentials["token"], _FAKE_TOKEN)
        self.assertNotIn("github_app", credentials)
        mock_resolve.assert_called_once_with("api.github.com")

    def test_plain_github_repository_has_no_app_helpers(self):
        # The non-App backend should be clean — App auth lives entirely on
        # GithubAppRepository now.
        self.assertFalse(hasattr(GithubRepository, "_resolve_github_app_token"))
        self.assertFalse(
            hasattr(GithubRepository, "_resolve_github_app_credentials_for_repo")
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "github-app-tests",
        }
    }
)
class TestGetInstallationToken(GitHubAppTestBase):
    def setUp(self):
        cache.clear()

    @patch("weblate.vcs.github.requests.post")
    def test_get_token(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"token": "ghs_test_token_123"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        token = get_installation_token("12345", self.private_key, "67890", "github.com")
        self.assertEqual(token, "ghs_test_token_123")
        self.assertEqual(
            mock_post.call_args[0][0],
            "https://api.github.com/app/installations/67890/access_tokens",
        )

    @patch("weblate.vcs.github.requests.post")
    def test_token_caching(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"token": "ghs_cached_token"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        token1 = get_installation_token(
            "12345", self.private_key, "67890", "github.com"
        )
        self.assertEqual(token1, "ghs_cached_token")
        self.assertEqual(mock_post.call_count, 1)

        token2 = get_installation_token(
            "12345", self.private_key, "67890", "github.com"
        )
        self.assertEqual(token2, "ghs_cached_token")
        self.assertEqual(mock_post.call_count, 1)

    @patch("weblate.vcs.github.requests.post")
    def test_cache_key_includes_hostname(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.side_effect = [
            {"token": "ghs_dotcom"},
            {"token": "ghs_enterprise"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        dotcom = get_installation_token(
            "12345", self.private_key, "67890", "github.com"
        )
        ghe = get_installation_token(
            "12345", self.private_key, "67890", "github.example.com"
        )
        self.assertNotEqual(dotcom, ghe)
        self.assertEqual(mock_post.call_count, 2)


class TestGitHubAppManifestHelpers(SimpleTestCase):
    def test_build_manifest_includes_expected_keys(self):
        manifest = build_github_app_manifest(
            name="Weblate",
            base_url="https://weblate.example.com/",
            redirect_url="https://weblate.example.com/cb/",
            setup_url="https://weblate.example.com/setup/",
            webhook_url="https://weblate.example.com/hook/",
        )
        self.assertEqual(manifest["name"], "Weblate")
        self.assertEqual(manifest["redirect_url"], "https://weblate.example.com/cb/")
        self.assertEqual(manifest["setup_url"], "https://weblate.example.com/setup/")
        self.assertTrue(manifest["setup_on_update"])
        # Default to public so GitHub's install URL shows the account picker.
        self.assertTrue(manifest["public"])
        self.assertEqual(
            manifest["hook_attributes"],
            {"url": "https://weblate.example.com/hook/", "active": True},
        )
        self.assertEqual(
            manifest["default_permissions"], dict(GITHUB_APP_MANIFEST_PERMISSIONS)
        )
        self.assertEqual(manifest["default_events"], list(GITHUB_APP_MANIFEST_EVENTS))

    def test_build_manifest_respects_private(self):
        manifest = build_github_app_manifest(
            name="Weblate",
            base_url="https://weblate.example.com/",
            redirect_url="https://weblate.example.com/cb/",
            setup_url="https://weblate.example.com/setup/",
            webhook_url="https://weblate.example.com/hook/",
            public=False,
        )
        self.assertFalse(manifest["public"])

    def test_manifest_new_url_personal(self):
        self.assertEqual(
            get_github_app_manifest_new_url("github.com"),
            "https://github.com/settings/apps/new",
        )

    def test_manifest_new_url_organization(self):
        self.assertEqual(
            get_github_app_manifest_new_url("github.com", "acme"),
            "https://github.com/organizations/acme/settings/apps/new",
        )

    def test_manifest_new_url_enterprise(self):
        self.assertEqual(
            get_github_app_manifest_new_url("github.example.com"),
            "https://github.example.com/settings/apps/new",
        )

    @patch("weblate.vcs.github.requests.post")
    def test_exchange_manifest_code(self, mock_post):
        mock_post.return_value = MagicMock(
            json=MagicMock(return_value={"id": 1, "slug": "weblate"}),
            raise_for_status=MagicMock(),
        )
        data = exchange_github_app_manifest_code("abc", "github.com")
        self.assertEqual(data, {"id": 1, "slug": "weblate"})
        self.assertEqual(
            mock_post.call_args[0][0],
            "https://api.github.com/app-manifests/abc/conversions",
        )

    @patch("weblate.vcs.github.requests.post")
    def test_exchange_manifest_code_enterprise(self, mock_post):
        mock_post.return_value = MagicMock(
            json=MagicMock(return_value={}),
            raise_for_status=MagicMock(),
        )
        exchange_github_app_manifest_code("abc", "github.example.com")
        self.assertEqual(
            mock_post.call_args[0][0],
            "https://github.example.com/api/v3/app-manifests/abc/conversions",
        )


class TestDatabaseCredentials(TestCase):
    def test_configurations_loaded_from_db(self):
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

    def test_no_configuration_without_db_row(self):
        self.assertEqual(get_github_app_configurations(), {})
        self.assertFalse(github_app_is_configured())

    def test_backend_always_registered(self):
        """
        The backend must stay in the cached VCS registry regardless of config.

        App credentials live in the database, so gating registry membership on
        them would hide the backend until a worker restart (see the import
        button preselecting the wrong VCS).
        """
        self.assertTrue(GithubAppRepository.is_configured())
        # Reload the registry with no App configured.
        VCS_REGISTRY.__dict__.pop("data", None)
        try:
            self.assertIn("github-app", VCS_REGISTRY.keys())
        finally:
            VCS_REGISTRY.__dict__.pop("data", None)


class TestVerifyWebhookSignature(SimpleTestCase):
    def _sign(self, payload: bytes, secret: str) -> str:
        return (
            "sha256="
            + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        )

    def test_valid_signature(self):
        payload = b'{"action": "push"}'
        self.assertTrue(
            verify_webhook_signature(payload, self._sign(payload, "s"), "s")
        )

    def test_invalid_signature(self):
        self.assertFalse(
            verify_webhook_signature(b'{"action": "push"}', "sha256=invalid", "s")
        )

    def test_missing_prefix(self):
        self.assertFalse(verify_webhook_signature(b"t", "invalid", "s"))

    def test_empty_signature(self):
        self.assertFalse(verify_webhook_signature(b"t", "", "s"))
