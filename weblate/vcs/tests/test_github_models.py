# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app models."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import responses
from django.core.cache import cache
from django.test import TestCase

from weblate.vcs.base import RepositoryError
from weblate.vcs.github import (
    GitHubAppCredentials,
    GitHubAppNotConfiguredError,
    GithubAppRepository,
    GitHubInstallation,
)
from weblate.vcs.tests.utils import generate_private_key
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.trans.models import Component

SETTINGS_PRIVATE_KEY = generate_private_key()


def _make_credentials(
    hostname: str = "github.com", **overrides
) -> GitHubAppCredentials:
    defaults = {
        "app_id": "99999",
        "app_slug": "weblate-app",
        "private_key": SETTINGS_PRIVATE_KEY,
        "webhook_secret": "credentials-secret",
    }
    defaults.update(overrides)
    return GitHubAppCredentials.objects.create(hostname=hostname, **defaults)


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

        self.assertIsNone(
            GitHubInstallation.objects.get_for_repo(
                "github.example.com", "test-org/repo1"
            )
        )

        self.assertIsNone(
            GitHubInstallation.objects.get_for_repo("github.com", "other/repo")
        )

        self.installation.enabled = False
        self.installation.save()
        self.assertIsNone(
            GitHubInstallation.objects.get_for_repo(
                "github.com",
                "test-org/repo1",
                workspace=self.installation.workspace,
            )
        )

    def test_get_for_installation(self):
        self.assertEqual(
            GitHubInstallation.objects.get_for_installation("github.com", "67890"),
            self.installation,
        )

    @responses.activate
    def test_sync_from_api(self):
        _make_credentials()
        responses.add(
            responses.GET,
            "https://api.github.com/app/installations/24680",
            json={
                "id": 24680,
                "app_id": 99999,
                "account": {"login": "synced-org", "type": "Organization"},
            },
        )

        installation = GitHubInstallation.objects.sync_from_api(
            "github.com", "24680", workspace=_make_workspace("sync-workspace")
        )

        self.assertEqual(installation.target_login, "synced-org")
        self.assertEqual(installation.app_id, "99999")
        self.assertEqual(len(responses.calls), 1)

    def test_sync_from_api_requires_credentials(self):
        with self.assertRaises(GitHubAppNotConfiguredError):
            GitHubInstallation.objects.sync_from_api(
                "github.com",
                "24680",
                workspace=_make_workspace("sync-missing-workspace"),
            )

    @responses.activate
    def test_github_repository_auth_args_use_installation_token(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )

        args = list(
            GithubAppRepository._get_auth_args(  # noqa: SLF001
                "https://github.com/test-org/repo1.git",
                workspace=self.installation.workspace,
            )
        )

        self.assertTrue(
            any("http.extraHeader=Authorization: Basic" in arg for arg in args)
        )
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://api.github.com/app/installations/67890/access_tokens",
        )

    @responses.activate
    def test_github_repository_auth_args_require_workspace(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )

        args = list(
            GithubAppRepository._get_auth_args(  # noqa: SLF001
                "https://github.com/test-org/repo1.git"
            )
        )

        self.assertFalse(
            any("http.extraHeader=Authorization: Basic" in arg for arg in args)
        )
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    def test_github_repository_instance_auth_requires_workspace(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )
        component = cast(
            "Component",
            SimpleNamespace(
                pk=None,
                full_slug="test/project/component",
                project_id=1,
                project=SimpleNamespace(workspace_id=None, workspace=None),
                repo="https://github.com/test-org/repo1.git",
            ),
        )
        repository = GithubAppRepository(
            ".", branch="main", component=component, local=True
        )

        self.assertEqual(repository.get_auth_args(), [])
        with self.assertRaises(RepositoryError):
            repository.get_credentials_by_hostname("api.github.com")
        self.assertEqual(len(responses.calls), 0)
