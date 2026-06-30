# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app models."""

from __future__ import annotations

from base64 import b64decode
from unittest.mock import patch

import responses
from django.core.cache import cache
from django.test import TestCase

from weblate.trans.models import Component, Project
from weblate.vcs.base import RepositoryError
from weblate.vcs.github import (
    GitHubAppCredentials,
    GitHubAppNotConfiguredError,
    GithubAppRepository,
    GitHubInstallation,
)
from weblate.vcs.tests.utils import generate_private_key
from weblate.workspaces.models import Workspace

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


def _assert_no_github_app_auth_args(testcase: TestCase, args: list[str]) -> None:
    testcase.assertFalse(
        any("http.extraHeader" in arg or "Authorization: Basic" in arg for arg in args)
    )


def _assert_github_app_auth_environment(
    testcase: TestCase, environment: dict[str, str]
) -> None:
    testcase.assertEqual(environment["GIT_CONFIG_COUNT"], "1")
    testcase.assertEqual(environment["GIT_CONFIG_KEY_0"], "http.extraHeader")
    testcase.assertEqual(
        b64decode(
            environment["GIT_CONFIG_VALUE_0"].removeprefix("Authorization: Basic ")
        ).decode("utf-8"),
        "x-access-token:ghs_test",
    )


class TestGitHubInstallationManager(TestCase):
    def setUp(self):
        self.installation = _make_installation(
            repositories=[{"full_name": "test-org/repo1"}]
        )

    def _make_component(
        self,
        repo: str = "https://github.com/test-org/repo1.git",
        *,
        has_workspace: bool = True,
        push: str = "",
    ) -> Component:
        project = Project(
            id=1,
            name="Test",
            slug="test",
            workspace=self.installation.workspace if has_workspace else None,
        )
        return Component(
            name="Component",
            slug="component",
            project=project,
            repo=repo,
            push=push,
        )

    def _make_app_repository(
        self, repo: str = "https://github.com/test-org/repo1.git"
    ) -> GithubAppRepository:
        component = self._make_component(repo)
        return GithubAppRepository(".", branch="main", component=component, local=True)

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
    def test_connect_workspace_reenables_existing_installation(self):
        _make_credentials()
        self.installation.enabled = False
        self.installation.save(update_fields=["enabled"])
        responses.add(
            responses.GET,
            "https://api.github.com/app/installations/67890",
            json={
                "id": 67890,
                "app_id": 99999,
                "account": {"login": "test-org", "type": "Organization"},
            },
        )

        installation, created = GitHubInstallation.objects.connect_workspace(
            "github.com", "67890", self.installation.workspace
        )

        self.assertFalse(created)
        self.assertEqual(installation.pk, self.installation.pk)
        self.assertTrue(installation.enabled)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_github_repository_auth_environment_uses_installation_token(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )
        repository = self._make_app_repository()

        args = repository.get_auth_args()
        environment = repository.get_auth_environment()

        _assert_no_github_app_auth_args(self, args)
        _assert_github_app_auth_environment(self, environment)
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://api.github.com/app/installations/67890/access_tokens",
        )

    def test_github_repository_remote_branch_requires_import_branch(self):
        with self.assertRaisesRegex(
            RepositoryError, "GitHub App repositories must be imported with a branch"
        ):
            GithubAppRepository.get_remote_branch(
                "https://github.com/test-org/repo1.git"
            )

    def test_github_component_does_not_guess_default_branch(self):
        component = Component(
            vcs=GithubAppRepository.identifier,
            repo="https://github.com/test-org/repo1.git",
            branch="",
        )

        component.set_default_branch()

        self.assertEqual(component.branch, "")

    @responses.activate
    def test_github_repository_auth_environment_requires_workspace(self):
        repository = GithubAppRepository(".", branch="main", local=True)

        with self.assertRaisesRegex(
            RepositoryError, "GitHub App components require a project with a workspace"
        ):
            repository.get_auth_environment()

        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    def test_github_repository_auth_environment_require_installation(self):
        _make_credentials()
        cache.clear()
        repository = self._make_app_repository("https://github.com/other/repo.git")

        with self.assertRaisesRegex(
            RepositoryError, "No Weblate GitHub app installation available"
        ):
            repository.get_auth_environment()

        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    def test_github_repository_auth_environment_token_failure_raises_repository_error(
        self,
    ):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            status=500,
        )
        repository = self._make_app_repository()

        with self.assertRaisesRegex(
            RepositoryError, "Could not obtain GitHub App access token"
        ):
            repository.get_auth_environment()

        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_github_repository_instance_auth_requires_workspace(self):
        component = self._make_component(has_workspace=False)
        repository = GithubAppRepository(
            ".", branch="main", component=component, local=True
        )

        with self.assertRaisesRegex(
            RepositoryError, "GitHub App components require a project with a workspace"
        ):
            repository.get_auth_environment()
        with self.assertRaisesRegex(
            RepositoryError, "GitHub App components require a project with a workspace"
        ):
            repository.get_credentials_by_hostname("api.github.com")
        self.assertEqual(len(responses.calls), 0)

    @responses.activate
    def test_github_repository_instance_auth_token_failure_raises_repository_error(
        self,
    ):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            status=500,
        )
        component = self._make_component()
        repository = GithubAppRepository(
            ".", branch="main", component=component, local=True
        )

        with self.assertRaisesRegex(
            RepositoryError, "Could not obtain GitHub App access token"
        ):
            repository.get_credentials_by_hostname("api.github.com")

        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_github_repository_clone_uses_installation_token(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )
        component = self._make_component()
        repository = GithubAppRepository(
            ".", branch="main", component=component, local=True
        )

        with patch.object(GithubAppRepository, "_popen", return_value="") as popen:
            repository.clone_from("https://github.com/test-org/repo1.git")

        clone_args = popen.call_args_list[-1].args[0]
        environment = popen.call_args_list[-1].kwargs["environment"]
        self.assertIn("clone", clone_args)
        _assert_no_github_app_auth_args(self, clone_args)
        _assert_github_app_auth_environment(self, environment)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_github_repository_push_uses_installation_token_environment(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )
        repository = self._make_app_repository()

        with (
            patch.object(GithubAppRepository, "execute", return_value="") as execute,
            patch.object(GithubAppRepository, "create_pull_request"),
            patch.object(GithubAppRepository, "validate_pull_url"),
        ):
            repository.push("weblate-test")

        push_args = execute.call_args.args[0]
        environment = execute.call_args.kwargs["environment"]
        self.assertIn("push", push_args)
        _assert_no_github_app_auth_args(self, push_args)
        _assert_github_app_auth_environment(self, environment)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_github_repository_remote_compatibility_deepen_uses_installation_token(
        self,
    ):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )
        component = self._make_component()
        repository = GithubAppRepository(
            ".", branch="main", component=component, local=True
        )

        with (
            patch.object(GithubAppRepository, "execute", return_value="") as execute,
            patch.object(
                GithubAppRepository,
                "get_config",
                return_value="https://github.com/test-org/repo1.git",
            ),
        ):
            repository.deepen_remote_compatibility_history("main")

        deepen_args = execute.call_args.args[0]
        environment = execute.call_args.kwargs["environment"]
        self.assertIn("fetch", deepen_args)
        self.assertIn(f"--deepen={repository.remote_compatibility_deepen}", deepen_args)
        _assert_no_github_app_auth_args(self, deepen_args)
        _assert_github_app_auth_environment(self, environment)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_github_repository_remote_compatibility_uses_installation_token(self):
        _make_credentials()
        cache.clear()
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_test"},
        )
        component = self._make_component()
        repository = GithubAppRepository(
            ".", branch="main", component=component, local=True
        )

        with (
            patch.object(GithubAppRepository, "_popen", return_value=""),
            patch.object(GithubAppRepository, "execute", return_value="") as execute,
            patch.object(GithubAppRepository, "has_common_history", return_value=True),
        ):
            repository.validate_remote_compatibility(
                "https://github.com/test-org/repo1.git", "main"
            )

        fetch_call = next(
            call for call in execute.call_args_list if "fetch" in call.args[0]
        )
        fetch_args = fetch_call.args[0]
        environment = fetch_call.kwargs["environment"]
        self.assertIn("fetch", fetch_args)
        _assert_no_github_app_auth_args(self, fetch_args)
        _assert_github_app_auth_environment(self, environment)
        self.assertEqual(len(responses.calls), 1)
