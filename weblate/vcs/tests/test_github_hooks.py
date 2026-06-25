# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app webhook event handling."""

from __future__ import annotations

import json

import responses
from django.core.cache import cache
from rest_framework.test import APIClient

from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.vcs.github import (
    GitHubAppCredentials,
    GitHubInstallation,
)
from weblate.vcs.models import InstallationProvider, PendingInstallation
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

    def setUp(self):
        super().setUp()
        # Webhook endpoints are unauthenticated; use a plain API client.
        self.client = APIClient()
        self.workspace = Workspace.objects.create(name="Hook Workspace")
        _make_credentials("github.com", GITHUB_COM_TOKEN, webhook_secret="s3cret")

    def _post(self, event_type, data, *, secret: str | None = "s3cret", url=None):  # noqa: S107
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

    def test_installation_deleted(self):
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

    def test_installation_suspended(self):
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

    def test_installation_unsuspended(self):
        self._create_installation(enabled=False)
        data = {
            "action": "unsuspend",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(GitHubInstallation.objects.get(installation_id="12345").enabled)

    @responses.activate
    def test_installation_created_syncs_existing_row(self):
        """``created`` updates rows owned by the setup flow; never auto-creates."""
        cache.clear()
        self._create_installation(target_login="placeholder")
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        responses.add(
            responses.GET,
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
                "account": {"login": "test-org", "type": "Organization"},
            },
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
            [call.request.method for call in responses.calls], ["POST", "GET"]
        )

    def test_installation_created_without_row_is_pending(self):
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
        self.assertEqual(pending.payload["action"], "created")

    def test_unknown_integration_token_is_rejected(self):
        """A delivery to an unknown integration token cannot be authenticated."""
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

    def test_repositories_added(self):
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

    def test_repositories_added_uses_installation_hostname(self):
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

    def test_repositories_removed(self):
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

    def test_installation_target_renamed_updates_components_and_repositories(self):
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

    def test_signature_required_when_secret_configured(self):
        """An App webhook on a configured integration requires a valid signature."""
        self._create_installation()
        data = {
            "action": "deleted",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data, secret=None)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(GitHubInstallation.objects.get(installation_id="12345").enabled)

    def test_invalid_signature_rejected(self):
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

    def test_other_integration_secret_does_not_authorize(self):
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

    def test_push_event(self):
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

    def _legacy_post(self, event_type, data):
        body = json.dumps(data)
        return self.client.post(
            self.LEGACY_WEBHOOK_URL,
            data=body,
            content_type="application/json",
            headers={"X-Github-Event": event_type},
        )

    def test_push_event_without_app_configured(self):
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

    def test_app_delivery_rejected_on_generic_endpoint(self):
        """GitHub App deliveries must use the per-integration endpoint."""
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

    def test_signed_integration_hook_runs_repository_update(self):
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
