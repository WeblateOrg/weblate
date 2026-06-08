# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Weblate GitHub app webhook event handling."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from weblate.vcs.github import GitHubAppCredentials, GitHubInstallation
from weblate.workspaces.models import Workspace

SETTINGS_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\nsettings\n-----END RSA PRIVATE KEY-----"
)

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


def _sign(body: str, secret: str) -> str:
    return (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )


class TestGitHubAppWebhookEvents(TestCase):
    WEBHOOK_URL = _integration_url(GITHUB_COM_TOKEN)

    def setUp(self):
        self.client = APIClient()
        self.workspace = Workspace.objects.create(name="Hook Workspace")
        _make_credentials("github.com", GITHUB_COM_TOKEN, webhook_secret="s3cret")

    def _post(self, event_type, data, *, secret="s3cret", url=None):  # noqa: S107
        body = json.dumps(data)
        headers = {
            "HTTP_X_GITHUB_EVENT": event_type,
            "content_type": "application/json",
        }
        if secret is not None:
            headers["HTTP_X_HUB_SIGNATURE_256"] = _sign(body, secret)
        return self.client.post(url or self.WEBHOOK_URL, data=body, **headers)

    def _create_installation(self, **overrides) -> GitHubInstallation:
        defaults = {
            "installation_id": "12345",
            "target_type": "Organization",
            "target_login": "test-org",
            "workspace": self.workspace,
        }
        defaults.update(overrides)
        return GitHubInstallation.objects.create(**defaults)

    # --- installation lifecycle -----------------------------------------

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

    @patch.object(GitHubInstallation, "refresh_repositories")
    def test_installation_created_syncs_existing_row(self, mock_refresh):
        """``created`` updates rows owned by the setup flow; never auto-creates."""
        self._create_installation(target_login="placeholder")
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
        mock_refresh.assert_called_once()

    def test_installation_created_without_row_is_noop(self):
        """Without a setup-created row, the App webhook does not auto-create one."""
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

    # --- repository changes ---------------------------------------------

    def test_repositories_added(self):
        installation = self._create_installation(
            repositories=[{"full_name": "test-org/existing"}]
        )
        data = {
            "action": "added",
            "installation": {"id": 12345},
            "repositories_added": [
                {
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
            "repositories_added": [{"full_name": "org/repo"}],
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

    # --- webhook signature enforcement ----------------------------------

    def test_signature_required_when_secret_configured(self):
        """An App webhook on a configured integration requires a valid signature."""
        self._create_installation()
        data = {
            "action": "deleted",
            "installation": {"id": 12345, "app_id": 99999, "account": {}},
        }
        response = self._post("installation", data, secret=None)
        self.assertEqual(response.status_code, 403)
        # The installation must not have been disabled
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

    def test_valid_signature_accepted(self):
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

    # --- push deliveries -------------------------------------------------

    def test_push_event_signed_by_configured_app(self):
        """Signed pushes from connected accounts are accepted."""
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
        response = self._post("push", data)
        self.assertIn(response.status_code, (200, 202))

    def test_push_event_without_app_signature(self):
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

    def test_ping_event_signed(self):
        # GitHub signs every delivery from a configured App, including pings.
        response = self._post("ping", {"zen": "keep it simple"})
        self.assertEqual(response.status_code, 201)


class TestGitHubLegacyWebhookEvents(TestCase):
    WEBHOOK_URL = "/hooks/github/"

    def setUp(self):
        self.client = APIClient()

    def _post(self, event_type, data, *, secret="s3cret"):  # noqa: S107
        body = json.dumps(data)
        headers = {
            "HTTP_X_GITHUB_EVENT": event_type,
            "content_type": "application/json",
        }
        if secret is not None:
            headers["HTTP_X_HUB_SIGNATURE_256"] = _sign(body, secret)
        return self.client.post(self.WEBHOOK_URL, data=body, **headers)

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
        response = self._post("push", data, secret=None)
        self.assertIn(response.status_code, (200, 202))

    def test_push_event_without_app_signature(self):
        """Plain repo-level webhook deliveries do not require the App secret."""
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
        response = self._post("push", data, secret=None)
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
        response = self._post("push", data)
        self.assertEqual(response.status_code, 403)
