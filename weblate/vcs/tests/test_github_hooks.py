# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app webhook event handling."""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.data import data_dir
from weblate.utils.tests import http_mock
from weblate.vcs.git import GitRepository
from weblate.vcs.github import (
    GitHubAppCredentials,
    GitHubInstallation,
)
from weblate.vcs.models import InstallationProvider, PendingInstallation
from weblate.vcs.pending import PENDING_GITHUB_INSTALLATION_RETENTION
from weblate.vcs.tasks import cleanup_pending_installations
from weblate.vcs.tests.utils import generate_private_key, sign_webhook_payload
from weblate.workspaces.models import Workspace

SETTINGS_PRIVATE_KEY = generate_private_key()

# Opaque webhook tokens identify which integration a delivery belongs to. They
# are part of the hook URL, so the host is known without guessing the payload.
GITHUB_COM_TOKEN = "11111111-1111-1111-1111-111111111111"
ENTERPRISE_TOKEN = "22222222-2222-2222-2222-222222222222"


def _make_credentials(
    hostname: str,
    webhook_token: str,
    *,
    webhook_secret: str,
    app_id: str = "99999",
    app_slug: str = "weblate-app",
) -> GitHubAppCredentials:
    return GitHubAppCredentials.objects.create(
        hostname=hostname,
        app_id=app_id,
        app_slug=app_slug,
        private_key=SETTINGS_PRIVATE_KEY,
        webhook_secret=webhook_secret,
        webhook_token=webhook_token,
    )


def _integration_url(token: str) -> str:
    return f"/hooks/integrations/{token}/"


class TestGitHubAppHooks(ViewTestCase):
    WEBHOOK_URL = _integration_url(GITHUB_COM_TOKEN)
    LEGACY_WEBHOOK_URL = "/hooks/github/"

    def setUp(self) -> None:
        super().setUp()
        # Webhook endpoints are unauthenticated; use a plain API client.
        self.client = APIClient()
        self.workspace = Workspace.objects.create(name="Hook Workspace")
        _make_credentials("github.com", GITHUB_COM_TOKEN, webhook_secret="s3cret")

    def _post(self, event_type, data, *, secret: str | None = "s3cret", url=None):  # ruff: ignore[hardcoded-password-default]
        body = json.dumps(data)
        headers = {"X-GitHub-Event": event_type}
        if secret:
            headers["X-Hub-Signature-256"] = sign_webhook_payload(body, secret)
        return self.client.post(
            url or self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers=headers,
        )

    def _create_installation(self, **overrides) -> GitHubInstallation:
        defaults = {
            "installation_id": "12345",
            "target_type": "Organization",
            "target_login": "test-org",
            "workspace": self.workspace,
        }
        defaults.update(overrides)
        return GitHubInstallation.objects.create(**defaults)

    def test_installation_deleted(self) -> None:
        self._create_installation()
        data = {
            "action": "deleted",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            GitHubInstallation.objects.get(installation_id="12345").enabled
        )

    def test_installation_suspended(self) -> None:
        self._create_installation()
        data = {
            "action": "suspend",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            GitHubInstallation.objects.get(installation_id="12345").enabled
        )

    def test_installation_unsuspended(self) -> None:
        self._create_installation(enabled=False)
        data = {
            "action": "unsuspend",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(GitHubInstallation.objects.get(installation_id="12345").enabled)

    @http_mock.activate
    def test_installation_created_syncs_existing_row(self) -> None:
        """``created`` updates rows owned by the setup flow; never auto-creates."""
        cache.clear()
        self._create_installation(target_login="placeholder")
        http_mock.register(
            "POST",
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        http_mock.register(
            "GET",
            "https://api.github.com/installation/repositories?per_page=100",
            json={
                "repositories": [
                    {
                        "name": "synced-repo",
                        "full_name": "test-org/synced-repo",
                        "clone_url": "https://github.com/test-org/synced-repo.git",
                        "ssh_url": "git@github.com:test-org/synced-repo.git",
                        "html_url": "https://github.com/test-org/synced-repo",
                    }
                ]
            },
        )
        data = {
            "action": "created",
            "installation": {
                "id": 12345,
                "app_id": 99999,
                "account": {
                    "login": "test-org",
                    "type": "Organization",
                    "avatar_url": "https://avatars.example/test-org",
                },
            },
            "repositories": [
                {
                    "name": "repo",
                    "full_name": "test-org/repo",
                    "private": False,
                    "description": "A repo",
                    "owner": {"login": "test-org"},
                }
            ],
            "sender": {"login": "octocat"},
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)

        installation = GitHubInstallation.objects.get(installation_id="12345")
        self.assertEqual(installation.target_login, "test-org")
        self.assertEqual(
            [r["full_name"] for r in installation.repositories],
            ["test-org/synced-repo"],
        )
        self.assertEqual(
            [call.request.method for call in http_mock.calls], ["POST", "GET"]
        )

    def test_installation_created_without_row_is_pending(self) -> None:
        """Without an authorized workspace row, the App webhook only stores metadata."""
        data = {
            "action": "created",
            "installation": {
                "id": 12345,
                "app_id": 99999,
                "account": {"login": "test-org", "type": "Organization"},
            },
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )
        pending = PendingInstallation.objects.get(
            provider=InstallationProvider.GITHUB,
            hostname="github.com",
            installation_id="12345",
        )
        self.assertEqual(
            pending.payload,
            {
                "action": "created",
                "installation": {
                    "id": 12345,
                    "app_id": 99999,
                    "account": {"login": "test-org", "type": "Organization"},
                },
            },
        )

    def test_installation_created_with_malformed_id_is_ignored(self) -> None:
        data = {
            "action": "created",
            "installation": {
                "id": "12345/access_tokens",
                "app_id": 99999,
                "account": {"login": "test-org", "type": "Organization"},
            },
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(GitHubInstallation.objects.exists())
        self.assertFalse(PendingInstallation.objects.exists())

    def test_cleanup_pending_installations_task(self) -> None:
        old = PendingInstallation.objects.create(
            provider=InstallationProvider.GITHUB,
            hostname="github.com",
            installation_id="old",
            payload={"action": "created"},
        )
        current = PendingInstallation.objects.create(
            provider=InstallationProvider.GITHUB,
            hostname="github.com",
            installation_id="current",
            payload={"action": "created"},
        )
        PendingInstallation.objects.filter(pk=old.pk).update(
            updated=timezone.now()
            - PENDING_GITHUB_INSTALLATION_RETENTION
            - timedelta(seconds=1)
        )

        cleanup_pending_installations()

        self.assertFalse(PendingInstallation.objects.filter(pk=old.pk).exists())
        self.assertTrue(PendingInstallation.objects.filter(pk=current.pk).exists())

    def test_unknown_webhook_token_is_rejected(self) -> None:
        """A delivery to an unknown webhook token cannot be authenticated."""
        data = {
            "action": "created",
            "installation": {
                "id": 99999,
                "app_id": 12345,
                "account": {"login": "stranger", "type": "User"},
            },
        }
        response = self._post(
            "installation",
            data,
            secret=None,
            url=_integration_url("33333333-3333-3333-3333-333333333333"),
        )
        self.assertEqual(response.status_code, 403)

    def test_repositories_added(self) -> None:
        installation = self._create_installation(
            repositories=[{"full_name": "test-org/existing"}]
        )
        data = {
            "action": "added",
            "installation": {"id": 12345},
            "repositories_added": [
                {
                    "name": "new-repo",
                    "full_name": "test-org/new-repo",
                    "private": False,
                    "description": "A new repo",
                }
            ],
            "repositories_removed": [],
        }
        response = self._post("installation_repositories", data)
        self.assertEqual(response.status_code, 201)
        installation.refresh_from_db()
        names = [r["full_name"] for r in installation.repositories]
        self.assertIn("test-org/existing", names)
        self.assertIn("test-org/new-repo", names)

    def test_repositories_added_uses_installation_hostname(self) -> None:
        _make_credentials(
            "github.example.com",
            ENTERPRISE_TOKEN,
            webhook_secret="enterprise-secret",
            app_id="11111",
            app_slug="weblate-enterprise-app",
        )
        installation = self._create_installation(
            hostname="github.example.com",
            repositories=[],
        )
        data = {
            "action": "added",
            "installation": {"id": 12345},
            "repositories_added": [{"name": "repo", "full_name": "org/repo"}],
            "repositories_removed": [],
        }
        response = self._post(
            "installation_repositories",
            data,
            secret="enterprise-secret",
            url=_integration_url(ENTERPRISE_TOKEN),
        )
        self.assertEqual(response.status_code, 201)
        installation.refresh_from_db()
        repo = installation.repositories[0]
        self.assertEqual(repo["clone_url"], "https://github.example.com/org/repo.git")
        self.assertEqual(repo["ssh_url"], "git@github.example.com:org/repo.git")

    def test_repositories_removed(self) -> None:
        installation = self._create_installation(
            repositories=[
                {"full_name": "test-org/repo1"},
                {"full_name": "test-org/repo2"},
            ]
        )
        data = {
            "action": "removed",
            "installation": {"id": 12345},
            "repositories_added": [],
            "repositories_removed": [{"full_name": "test-org/repo1"}],
        }
        response = self._post("installation_repositories", data)
        self.assertEqual(response.status_code, 201)
        installation.refresh_from_db()
        names = [r["full_name"] for r in installation.repositories]
        self.assertNotIn("test-org/repo1", names)
        self.assertIn("test-org/repo2", names)

    def test_installation_target_renamed_updates_components_and_repositories(
        self,
    ) -> None:
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])
        old_clone_url = "https://github.com/old-org/local-repo.git"
        new_clone_url = "https://github.com/new-org/local-repo.git"
        Component.objects.filter(pk=self.component.pk).update(
            vcs="github-app",
            repo=old_clone_url,
            push=old_clone_url,
            push_branch="translations",
        )
        installation = self._create_installation(
            target_login="old-org",
            repositories=[
                {
                    "full_name": "old-org/local-repo",
                    "clone_url": old_clone_url,
                    "ssh_url": "git@github.com:old-org/local-repo.git",
                    "html_url": "https://github.com/old-org/local-repo",
                    "default_branch": self.component.branch,
                    "private": False,
                    "description": "",
                }
            ],
        )
        data = {
            "action": "renamed",
            "installation": {"id": 12345, "app_id": 99999},
            "account": {"login": "new-org", "type": "Organization"},
            "changes": {"login": {"from": "old-org"}},
            "target_type": "Organization",
        }

        response = self._post("installation_target", data)

        self.assertEqual(response.status_code, 201)
        installation.refresh_from_db()
        self.assertEqual(installation.target_login, "new-org")
        repo = installation.repositories[0]
        self.assertEqual(repo["full_name"], "new-org/local-repo")
        self.assertEqual(repo["clone_url"], new_clone_url)
        self.assertEqual(repo["ssh_url"], "git@github.com:new-org/local-repo.git")
        self.assertEqual(repo["html_url"], "https://github.com/new-org/local-repo")
        self.component.refresh_from_db()
        self.assertEqual(self.component.repo, new_clone_url)
        self.assertEqual(self.component.push, "")
        self.assertEqual(self.component.push_branch, "")

    def test_signature_required_when_secret_configured(self) -> None:
        """An App webhook on a configured integration requires a valid signature."""
        self._create_installation()
        data = {
            "action": "deleted",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data, secret=None)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(GitHubInstallation.objects.get(installation_id="12345").enabled)

    def test_invalid_signature_rejected(self) -> None:
        self._create_installation()
        data = {
            "action": "deleted",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        body = json.dumps(data)
        response = self.client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers={
                "x-github-event": "installation",
                "x-hub-signature-256": "sha256=0" * 32,
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_other_integration_secret_does_not_authorize(self) -> None:
        """Signing with another integration's secret must be rejected."""
        _make_credentials(
            "github.example.com",
            ENTERPRISE_TOKEN,
            webhook_secret="enterprise-secret",
            app_id="11111",
            app_slug="weblate-enterprise-app",
        )
        self._create_installation(
            installation_id="12345", hostname="github.example.com"
        )
        data = {
            "action": "deleted",
            "installation": {
                "id": 12345,
                "app_id": 11111,
                "account": {
                    "html_url": "https://github.example.com/test-org",
                },
            },
        }
        # Deliver to the enterprise integration URL but sign with github.com's
        # secret; only the enterprise secret may authenticate this endpoint.
        response = self._post(
            "installation",
            data,
            secret="s3cret",
            url=_integration_url(ENTERPRISE_TOKEN),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(GitHubInstallation.objects.get(installation_id="12345").enabled)

    def test_push_event(self) -> None:
        """GitHub App deliveries require the integration secret."""
        data = {
            "ref": "refs/heads/main",
            "installation": {"id": 12345, "app_id": 99999},
            "repository": {
                "name": "test-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/test-repo",
                "clone_url": "https://github.com/test-org/test-repo.git",
                "ssh_url": "git@github.com:test-org/test-repo.git",
                "html_url": "https://github.com/test-org/test-repo",
            },
        }
        response = self._post("push", data, secret=None)
        self.assertEqual(response.status_code, 403)
        response = self._post("push", data)
        self.assertIn(response.status_code, (200, 202))

    def _legacy_post(
        self,
        event_type,
        data,
        *,
        secret: str | None = None,
        signature: str | None = None,
    ):
        body = json.dumps(data)
        headers = {"X-Github-Event": event_type}
        if signature is not None:
            headers["X-Hub-Signature-256"] = signature
        elif secret is not None:
            headers["X-Hub-Signature-256"] = sign_webhook_payload(body, secret)
        return self.client.post(
            self.LEGACY_WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers=headers,
        )

    def test_push_event_without_app_configured(self) -> None:
        """Plain repo-level webhook deliveries still work when no App is set up."""
        data = {
            "ref": "refs/heads/main",
            "repository": {
                "name": "test-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/test-repo",
                "clone_url": "https://github.com/test-org/test-repo.git",
                "ssh_url": "git@github.com:test-org/test-repo.git",
                "html_url": "https://github.com/test-org/test-repo",
            },
        }
        response = self._legacy_post("push", data)
        self.assertIn(response.status_code, (200, 202))

    def test_app_delivery_rejected_on_generic_endpoint(self) -> None:
        """App deliveries are rejected unless a legacy secret is configured."""
        data = {
            "ref": "refs/heads/main",
            "installation": {"id": 12345, "app_id": 99999},
            "repository": {
                "name": "test-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/test-repo",
                "clone_url": "https://github.com/test-org/test-repo.git",
                "ssh_url": "git@github.com:test-org/test-repo.git",
                "html_url": "https://github.com/test-org/test-repo",
            },
        }
        response = self._post("push", data, url=self.LEGACY_WEBHOOK_URL)
        self.assertEqual(response.status_code, 403)

    @override_settings(GITHUB_LEGACY_APP_WEBHOOK_SECRET="legacy-secret")
    def test_legacy_app_push_with_valid_signature(self) -> None:
        """A signed legacy App push updates ordinary Git components."""
        data = {
            "ref": f"refs/heads/{self.component.branch}",
            "installation": {"id": 12345},
            "repository": {
                "name": "local-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/local-repo",
                "clone_url": self.component.repo,
            },
        }

        response = self._legacy_post("push", data, secret="legacy-secret")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.component.change_set.filter(action=ActionEvents.HOOK).exists()
        )

    @override_settings(GITHUB_LEGACY_APP_WEBHOOK_SECRET="legacy-secret")
    def test_legacy_app_push_rejects_invalid_signatures(self) -> None:
        data = {
            "ref": "refs/heads/main",
            "installation": {"id": 12345},
            "repository": {
                "name": "test-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/test-repo",
                "clone_url": "https://github.com/test-org/test-repo.git",
            },
        }
        signatures = (
            {"secret": None},
            {"secret": "wrong-secret"},
            {"signature": "invalid"},
        )

        for signature in signatures:
            with self.subTest(signature=signature):
                response = self._legacy_post("push", data, **signature)
                self.assertEqual(response.status_code, 403)

    @override_settings(GITHUB_LEGACY_APP_WEBHOOK_SECRET="legacy-secret")
    def test_legacy_app_push_excludes_github_app_components(self) -> None:
        self.component.vcs = "github-app"
        self.component.save(update_fields=["vcs"])
        data = {
            "ref": f"refs/heads/{self.component.branch}",
            "installation": {"id": 12345},
            "repository": {
                "name": "local-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/local-repo",
                "clone_url": self.component.repo,
            },
        }

        response = self._legacy_post("push", data, secret="legacy-secret")

        self.assertEqual(response.status_code, 202)
        self.assertFalse(
            self.component.change_set.filter(action=ActionEvents.HOOK).exists()
        )

    @override_settings(GITHUB_LEGACY_APP_WEBHOOK_SECRET="legacy-secret")
    def test_legacy_app_non_push_event_is_ignored(self) -> None:
        installation = self._create_installation()
        data = {
            "action": "deleted",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }

        response = self._legacy_post("installation", data, secret="legacy-secret")

        self.assertEqual(response.status_code, 201)
        installation.refresh_from_db()
        self.assertTrue(installation.enabled)

    def test_signed_integration_hook_runs_repository_update(self) -> None:
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[
                {
                    "full_name": "test-org/local-repo",
                    "clone_url": self.component.repo,
                    "ssh_url": "git@github.com:test-org/local-repo.git",
                    "html_url": "https://github.com/test-org/local-repo",
                    "default_branch": self.component.branch,
                    "private": False,
                    "description": "",
                }
            ],
        )
        self.component.vcs = "github-app"
        self.component.save(update_fields=["vcs"])

        payload = {
            "ref": f"refs/heads/{self.component.branch}",
            "installation": {"id": 12345, "app_id": 99999},
            "repository": {
                "name": "local-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/local-repo",
                "clone_url": self.component.repo,
                "ssh_url": "git@github.com:test-org/local-repo.git",
                "html_url": "https://github.com/test-org/local-repo",
            },
        }
        body = json.dumps(payload)

        response = self.client.post(
            self.WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers={
                "x-github-event": "push",
                "x-hub-signature-256": sign_webhook_payload(body, "s3cret"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.component.full_slug, response.json()["message"])
        self.assertTrue(
            self.component.change_set.filter(action=ActionEvents.HOOK).exists()
        )

    def test_signed_integration_hook_respects_disabled_project_hooks(self) -> None:
        self.project.workspace = self.workspace
        self.project.enable_hooks = False
        self.project.save(update_fields=["workspace", "enable_hooks"])
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[
                {
                    "full_name": "test-org/local-repo",
                    "clone_url": self.component.repo,
                    "ssh_url": "git@github.com:test-org/local-repo.git",
                    "html_url": "https://github.com/test-org/local-repo",
                    "default_branch": self.component.branch,
                    "private": False,
                    "description": "",
                }
            ],
        )
        self.component.vcs = "github-app"
        self.component.save(update_fields=["vcs"])

        payload = {
            "ref": f"refs/heads/{self.component.branch}",
            "installation": {"id": 12345, "app_id": 99999},
            "repository": {
                "name": "local-repo",
                "owner": {"login": "test-org"},
                "url": "https://github.com/test-org/local-repo",
                "clone_url": self.component.repo,
                "ssh_url": "git@github.com:test-org/local-repo.git",
                "html_url": "https://github.com/test-org/local-repo",
            },
        }

        response = self._post("push", payload)

        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )
        self.assertEqual(response.json()["match_status"]["repository_matches"], 1)
        self.assertEqual(response.json()["match_status"]["branch_matches"], 1)
        self.assertEqual(response.json()["match_status"]["enabled_hook_matches"], 0)
        self.assertFalse(
            self.component.change_set.filter(action=ActionEvents.HOOK).exists()
        )


def _api_repository(full_name: str) -> dict:
    return {
        "name": full_name.split("/")[1],
        "full_name": full_name,
        "clone_url": f"https://github.com/{full_name}.git",
        "ssh_url": f"git@github.com:{full_name}.git",
        "html_url": f"https://github.com/{full_name}",
        "default_branch": "main",
        "private": False,
        "description": "",
    }


class RefreshGitHubRepositoriesTest(ViewTestCase):
    """
    Refreshing repositories retargets components of moved repositories.

    Only the GitHub API is mocked. Git URLs of GitHub repositories are routed
    to the local test repository, so components really fetch from them.
    """

    OLD_URL = "https://github.com/test-org/old-repo.git"
    NEW_URL = "https://github.com/test-org/new-repo.git"

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        http_mock.start()
        self.addCleanup(http_mock.stop)
        # Weblate manages ~/.gitconfig, keep the rewrites in the XDG config
        self.gitconfig = Path(data_dir("home")) / ".config" / "git" / "config"
        self.gitconfig.parent.mkdir(parents=True, exist_ok=True)
        if self.gitconfig.exists():
            self.addCleanup(self.gitconfig.write_text, self.gitconfig.read_text())
        else:
            self.addCleanup(self.gitconfig.unlink, missing_ok=True)
        self.local_repo = self.format_local_path(self.git_repo_path)

        self.workspace = Workspace.objects.create(name="Refresh Workspace")
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])
        _make_credentials("github.com", GITHUB_COM_TOKEN, webhook_secret="s3cret")
        http_mock.register(
            "POST",
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        self.installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_api_repository("test-org/old-repo")],
        )
        self._convert_component(self.OLD_URL)

    def _route_git(self, *urls: str) -> None:
        """Make only the given GitHub URLs reachable for git."""
        self.gitconfig.write_text(
            "".join(f'[url "{self.local_repo}"]\n\tinsteadOf = {url}\n' for url in urls)
        )

    def _convert_component(self, url: str, vcs: str = "github-app") -> None:
        self._route_git(url)
        self.component.vcs = vcs
        self.component.repo = url
        self.component.save()

    def _register_repositories(self, *full_names: str) -> None:
        http_mock.register(
            "GET",
            "https://api.github.com/installation/repositories?per_page=100",
            json={"repositories": [_api_repository(name) for name in full_names]},
        )

    def _register_lookup(self, full_name: str, current_full_name: str) -> None:
        # GitHub redirects the old name, the client ends with the current data
        http_mock.register(
            "GET",
            f"https://api.github.com/repos/{full_name}",
            json=_api_repository(current_full_name),
        )

    def _api_urls(self) -> list[str]:
        return [str(call.request.url) for call in http_mock.calls]

    def _post_repository_event(self, action: str, **overrides) -> None:
        data = {
            "action": action,
            "installation": {"id": 12345},
            "repository": _api_repository("test-org/new-repo"),
            **overrides,
        }
        body = json.dumps(data)
        response = APIClient().post(
            _integration_url(GITHUB_COM_TOKEN),
            data=body,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "repository",
                "X-Hub-Signature-256": sign_webhook_payload(body, "s3cret"),
            },
        )
        self.assertEqual(response.status_code, 201, response.content)

    def assert_component_repo(self, url: str) -> None:
        self.component.refresh_from_db()
        self.assertEqual(self.component.repo, url)
        repository = self.component.repository
        assert isinstance(repository, GitRepository)
        self.assertEqual(repository.get_config("remote.origin.url"), url)

    def test_retargets_renamed_repository(self) -> None:
        self._route_git(self.NEW_URL)
        self._register_repositories("test-org/new-repo")
        self._register_lookup("test-org/old-repo", "test-org/new-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.installation.refresh_from_db()
        self.assertEqual(
            [repo["full_name"] for repo in self.installation.repositories],
            ["test-org/new-repo"],
        )
        self.assert_component_repo(self.NEW_URL)
        change = self.component.change_set.get(
            action=ActionEvents.COMPONENT_SETTING_CHANGE
        )
        self.assertEqual(change.details["old"], self.OLD_URL)
        self.assertEqual(change.details["target"], self.NEW_URL)

    def test_update_clears_failure_alert(self) -> None:
        # The repository is gone from the old URL
        self._route_git(self.NEW_URL)
        self.assertFalse(self.component.do_update())
        self.assertTrue(self.component.alert_set.filter(name="UpdateFailure").exists())
        self._register_repositories("test-org/new-repo")
        self._register_lookup("test-org/old-repo", "test-org/new-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.NEW_URL)
        self.assertFalse(self.component.alert_set.filter(name="UpdateFailure").exists())

    def test_ignores_repository_not_accessible_to_account(self) -> None:
        self._register_repositories("test-org/other")
        self._register_lookup("test-org/old-repo", "elsewhere/new-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.OLD_URL)

    def test_ignores_deleted_repository(self) -> None:
        self._register_repositories("test-org/other")
        http_mock.register(
            "GET",
            "https://api.github.com/repos/test-org/old-repo",
            status_code=404,
            json={"message": "Not Found"},
        )

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.OLD_URL)

    def test_skips_lookup_for_listed_repository(self) -> None:
        self._register_repositories("test-org/old-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.OLD_URL)
        self.assertNotIn(
            "https://api.github.com/repos/test-org/old-repo", self._api_urls()
        )

    def test_reports_failed_account(self) -> None:
        http_mock.register(
            "GET",
            "https://api.github.com/installation/repositories?per_page=100",
            status_code=500,
            json={},
        )

        with self.assertRaises(CommandError):
            call_command(
                "refresh_github_repositories", stdout=StringIO(), stderr=StringIO()
            )

        self.assert_component_repo(self.OLD_URL)

    def test_matches_repository_case_insensitively(self) -> None:
        old_url = "https://github.com/Test-Org/old-repo.git"
        self.installation.repositories = [_api_repository("Test-Org/old-repo")]
        self.installation.save(update_fields=["repositories"])
        self._convert_component(old_url)
        self._route_git(self.NEW_URL)
        self._register_repositories("test-org/new-repo")
        self._register_lookup("Test-Org/old-repo", "test-org/new-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.NEW_URL)

    def test_ignores_component_in_other_workspace(self) -> None:
        self.project.workspace = Workspace.objects.create(name="Other Workspace")
        self.project.save(update_fields=["workspace"])
        self._register_repositories("test-org/new-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.OLD_URL)
        self.assertNotIn(
            "https://api.github.com/repos/test-org/old-repo", self._api_urls()
        )

    def test_ignores_component_not_using_app(self) -> None:
        self._convert_component(self.OLD_URL, vcs="git")
        self._register_repositories("test-org/new-repo")

        call_command("refresh_github_repositories", stdout=StringIO())

        self.assert_component_repo(self.OLD_URL)
        self.assertNotIn(
            "https://api.github.com/repos/test-org/old-repo", self._api_urls()
        )

    def test_renamed_event_retargets_components(self) -> None:
        self._route_git(self.NEW_URL)
        self._register_repositories("test-org/new-repo")
        self._register_lookup("test-org/old-repo", "test-org/new-repo")

        self._post_repository_event(
            "renamed", changes={"repository": {"name": {"from": "old-repo"}}}
        )

        self.installation.refresh_from_db()
        self.assertEqual(
            [repo["full_name"] for repo in self.installation.repositories],
            ["test-org/new-repo"],
        )
        self.assert_component_repo(self.NEW_URL)
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.COMPONENT_SETTING_CHANGE
            ).exists()
        )

    def test_transferred_event_retargets_components(self) -> None:
        new_url = "https://github.com/other-org/old-repo.git"
        self._route_git(new_url)
        self._register_repositories("other-org/old-repo")
        self._register_lookup("test-org/old-repo", "other-org/old-repo")

        self._post_repository_event(
            "transferred", repository=_api_repository("other-org/old-repo")
        )

        self.assert_component_repo(new_url)

    def test_transfer_from_source_installation_refreshes_destination(self) -> None:
        new_url = "https://github.com/other-org/old-repo.git"
        self._route_git(new_url)
        destination = GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="other-org",
            workspace=self.workspace,
        )
        http_mock.register(
            "POST",
            "https://api.github.com/app/installations/67890/access_tokens",
            json={"token": "ghs_destination"},
        )
        for token, repositories in (
            ("ghs_test", []),
            ("ghs_destination", [_api_repository("other-org/old-repo")]),
        ):
            match = [http_mock.header_matcher({"Authorization": f"token {token}"})]
            http_mock.register(
                "GET",
                "https://api.github.com/installation/repositories?per_page=100",
                json={"repositories": repositories},
                match=match,
            )
            http_mock.register(
                "GET",
                "https://api.github.com/repos/test-org/old-repo",
                status_code=200 if repositories else 404,
                json=_api_repository("other-org/old-repo") if repositories else {},
                match=match,
            )

        self._post_repository_event(
            "transferred", repository=_api_repository("other-org/old-repo")
        )

        self.installation.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(self.installation.repositories, [])
        self.assertEqual(
            [repo["full_name"] for repo in destination.repositories],
            ["other-org/old-repo"],
        )
        self.assert_component_repo(new_url)

    def test_unsuspend_repairs_other_workspace(self) -> None:
        other_workspace = Workspace.objects.create(name="Other Refresh Workspace")
        other_installation = GitHubInstallation.objects.create(
            installation_id=self.installation.installation_id,
            target_type="Organization",
            target_login=self.installation.target_login,
            workspace=other_workspace,
            repositories=self.installation.repositories,
            enabled=False,
        )
        self.installation.enabled = False
        self.installation.save(update_fields=["enabled"])
        self.project.workspace = other_workspace
        self.project.save(update_fields=["workspace"])
        self._route_git(self.NEW_URL)
        self._register_repositories("test-org/new-repo")
        self._register_lookup("test-org/old-repo", "test-org/new-repo")
        body = json.dumps(
            {"action": "unsuspend", "installation": {"id": 12345, "app_id": 99999}}
        )

        response = APIClient().post(
            _integration_url(GITHUB_COM_TOKEN),
            data=body,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "installation",
                "X-Hub-Signature-256": sign_webhook_payload(body, "s3cret"),
            },
        )

        self.assertEqual(response.status_code, 201)
        self.installation.refresh_from_db()
        other_installation.refresh_from_db()
        self.assertTrue(self.installation.enabled)
        self.assertTrue(other_installation.enabled)
        self.assertEqual(
            other_installation.repositories, self.installation.repositories
        )
        self.assertEqual(
            self._api_urls().count(
                "https://api.github.com/installation/repositories?per_page=100"
            ),
            1,
        )
        self.assert_component_repo(self.NEW_URL)

    def test_redelivered_event_keeps_reused_name(self) -> None:
        # A new repository took over the old name after the rename
        self._register_repositories("test-org/old-repo", "test-org/new-repo")

        self._post_repository_event(
            "renamed", changes={"repository": {"name": {"from": "old-repo"}}}
        )

        self.assert_component_repo(self.OLD_URL)
        self.assertNotIn(
            "https://api.github.com/repos/test-org/old-repo", self._api_urls()
        )

    def test_other_repository_event_is_ignored(self) -> None:
        self._post_repository_event("edited")

        self.assertNotIn(
            "https://api.github.com/installation/repositories?per_page=100",
            self._api_urls(),
        )
        self.assert_component_repo(self.OLD_URL)

    def test_event_for_unknown_installation_is_ignored(self) -> None:
        self._post_repository_event("renamed", installation={"id": 999})

        self.assertNotIn(
            "https://api.github.com/installation/repositories?per_page=100",
            self._api_urls(),
        )
        self.assert_component_repo(self.OLD_URL)
