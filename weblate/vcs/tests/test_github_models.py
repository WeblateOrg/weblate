# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app models."""

from __future__ import annotations

from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from weblate.vcs.git import GithubRepository
from weblate.vcs.github import (
    GitHubAppNotConfiguredError,
    GitHubInstallation,
)
from weblate.workspaces.models import Workspace

SETTINGS_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\nsettings\n-----END RSA PRIVATE KEY-----"
)

GITHUB_COM_CREDENTIALS = {
    "github.com": {
        "app_id": "99999",
        "app_slug": "weblate-app",
        "private_key": SETTINGS_PRIVATE_KEY,
        "webhook_secret": "settings-secret",
    }
}


def _make_workspace(name: str = "github-workspace") -> Workspace:
    workspace, _created = Workspace.objects.get_or_create(name=name)
    return workspace


def _make_installation(**overrides) -> GitHubInstallation:
    defaults = {
        "installation_id": "67890",
        "target_type": "Organization",
        "target_login": "test-org",
        "hostname": "github.com",
        "workspace": _make_workspace(),
    }
    defaults.update(overrides)
    return GitHubInstallation.objects.create(**defaults)


class TestGitHubInstallation(TestCase):
    def setUp(self):
        self.installation = _make_installation()

    def test_str(self):
        self.assertEqual(str(self.installation), "test-org (github.com/67890)")

    def test_api_base_github(self):
        self.assertEqual(self.installation.api_base, "https://api.github.com")

    def test_api_base_ghe(self):
        self.installation.hostname = "github.example.com"
        self.assertEqual(
            self.installation.api_base, "https://github.example.com/api/v3"
        )

    def test_has_repository(self):
        self.installation.repositories = [
            {"full_name": "test-org/repo1"},
            {"full_name": "test-org/repo2"},
        ]
        self.installation.save()
        self.assertTrue(self.installation.has_repository("test-org/repo1"))
        self.assertFalse(self.installation.has_repository("test-org/repo3"))

    def test_has_repository_empty(self):
        self.assertFalse(self.installation.has_repository("test-org/repo1"))

    @override_settings(GITHUB_APP_CREDENTIALS=GITHUB_COM_CREDENTIALS)
    def test_get_webhook_secret_uses_settings(self):
        self.assertEqual(self.installation.get_webhook_secret(), "settings-secret")

    def test_get_webhook_secret_without_settings(self):
        self.assertEqual(self.installation.get_webhook_secret(), "")

    @override_settings(GITHUB_APP_CREDENTIALS=GITHUB_COM_CREDENTIALS)
    def test_app_id_from_settings(self):
        self.assertEqual(self.installation.app_id, "99999")

    def test_app_id_without_settings(self):
        self.assertEqual(self.installation.app_id, "")

    def test_get_access_token_requires_settings(self):
        with self.assertRaises(GitHubAppNotConfiguredError):
            self.installation.get_access_token()

    def test_refresh_repositories_requires_settings(self):
        with self.assertRaises(GitHubAppNotConfiguredError):
            self.installation.refresh_repositories()

    def test_same_installation_id_across_hosts(self):
        """The same installation ID may exist on github.com and a GHE host."""
        other = _make_installation(hostname="github.example.com")
        self.assertNotEqual(self.installation.pk, other.pk)

    def test_unique_per_host(self):
        with (
            transaction.atomic(),
            self.assertRaises(IntegrityError),
        ):
            _make_installation()

    def test_same_installation_id_across_workspaces(self):
        """The same installation ID may be connected to multiple workspaces."""
        other = _make_installation(workspace=_make_workspace("other-workspace"))
        self.assertNotEqual(self.installation.pk, other.pk)


class TestGitHubInstallationManager(TestCase):
    def setUp(self):
        self.installation = _make_installation(
            repositories=[{"full_name": "test-org/repo1"}]
        )

    def test_get_for_repo(self):
        self.assertEqual(
            GitHubInstallation.objects.get_for_repo("github.com", "test-org/repo1"),
            self.installation,
        )

    def test_get_for_repo_workspace_scope(self):
        other_workspace = _make_workspace("other-workspace")
        other = _make_installation(
            installation_id="99999",
            workspace=other_workspace,
            repositories=[{"full_name": "test-org/repo1"}],
        )

        self.assertEqual(
            GitHubInstallation.objects.get_for_repo(
                "github.com",
                "test-org/repo1",
                workspace=self.installation.workspace,
            ),
            self.installation,
        )
        self.assertEqual(
            GitHubInstallation.objects.get_for_repo(
                "github.com", "test-org/repo1", workspace=other_workspace
            ),
            other,
        )

    def test_get_for_repo_wrong_host(self):
        self.assertIsNone(
            GitHubInstallation.objects.get_for_repo(
                "github.example.com", "test-org/repo1"
            )
        )

    def test_get_for_repo_disabled(self):
        self.installation.enabled = False
        self.installation.save()
        self.assertIsNone(
            GitHubInstallation.objects.get_for_repo("github.com", "test-org/repo1")
        )

    def test_get_for_repo_not_found(self):
        self.assertIsNone(
            GitHubInstallation.objects.get_for_repo("github.com", "other/repo")
        )

    def test_get_for_installation(self):
        self.assertEqual(
            GitHubInstallation.objects.get_for_installation("github.com", "67890"),
            self.installation,
        )

    @override_settings(GITHUB_APP_CREDENTIALS=GITHUB_COM_CREDENTIALS)
    @patch("weblate.vcs.github.get_app_installation")
    def test_sync_from_api(self, mock_get_installation):
        mock_get_installation.return_value = {
            "id": 24680,
            "app_id": 99999,
            "account": {"login": "synced-org", "type": "Organization"},
        }

        installation = GitHubInstallation.objects.sync_from_api(
            "github.com", "24680", workspace=_make_workspace("sync-workspace")
        )

        self.assertEqual(installation.target_login, "synced-org")
        self.assertEqual(installation.app_id, "99999")

    def test_sync_from_api_requires_settings(self):
        with self.assertRaises(GitHubAppNotConfiguredError):
            GitHubInstallation.objects.sync_from_api(
                "github.com",
                "24680",
                workspace=_make_workspace("sync-missing-workspace"),
            )

    @override_settings(GITHUB_APP_CREDENTIALS=GITHUB_COM_CREDENTIALS)
    @patch.object(GitHubInstallation, "get_access_token", return_value="ghs_test")
    def test_github_repository_auth_args_use_installation_token(self, mock_token):
        args = list(
            GithubRepository._get_auth_args(  # noqa: SLF001
                "https://github.com/test-org/repo1.git"
            )
        )

        self.assertTrue(
            any("http.extraHeader=Authorization: Basic" in arg for arg in args)
        )
        self.assertEqual(mock_token.call_count, 1)
