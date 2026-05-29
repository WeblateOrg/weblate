# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.models import Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_another_user
from weblate.vcs.github import GitHubAppCredentials, GitHubInstallation
from weblate.workspaces.models import Workspace

SETTINGS_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\nsettings\n-----END RSA PRIVATE KEY-----"
)


def _ensure_workspace(project: Project, name: str = "Test Workspace") -> Workspace:
    if project.workspace_id is not None:
        return project.workspace
    workspace = Workspace.objects.create(name=name)
    project.workspace = workspace
    project.save(update_fields=["workspace"])
    return workspace


@override_settings(
    GITHUB_APP_CREDENTIALS={
        "github.com": {
            "app_id": "99999",
            "app_slug": "weblate-app",
            "private_key": SETTINGS_PRIVATE_KEY,
            "webhook_secret": "s3cret",
        }
    }
)
class GitHubInstallationViewTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        self.workspace = _ensure_workspace(self.project)

    def _start_install(self, next_url: str | None = None) -> str:
        url = reverse("github-app-install")
        params = {"workspace": str(self.workspace.pk)}
        if next_url is not None:
            params["next"] = next_url
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 302)
        return response["Location"]

    def test_install_redirects_to_github(self):
        location = self._start_install(reverse("github-app-repositories"))
        parsed = urlparse(location)

        self.assertEqual(parsed.netloc, "github.com")
        self.assertEqual(parsed.path, "/apps/weblate-app/installations/select_target")
        self.assertIn("state", parse_qs(parsed.query))

    @override_settings(
        GITHUB_APP_CREDENTIALS={
            "github.com": {
                "app_id": "99999",
                "app_slug": "weblate-app",
                "private_key": SETTINGS_PRIVATE_KEY,
                "webhook_secret": "s3cret",
            },
            "github.example.com": {
                "app_id": "11111",
                "app_slug": "weblate-enterprise-app",
                "private_key": SETTINGS_PRIVATE_KEY,
                "webhook_secret": "enterprise-secret",
            },
        }
    )
    def test_install_requires_host_selection_with_multiple_configs(self):
        response = self.client.get(
            reverse("github-app-install"),
            {
                "next": reverse("github-app-repositories"),
                "workspace": str(self.workspace.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "github.com")
        self.assertContains(response, "github.example.com")

    @override_settings(
        GITHUB_APP_CREDENTIALS={
            "github.com": {
                "app_id": "99999",
                "app_slug": "weblate-app",
                "private_key": SETTINGS_PRIVATE_KEY,
                "webhook_secret": "s3cret",
            },
            "github.example.com": {
                "app_id": "11111",
                "app_slug": "weblate-enterprise-app",
                "private_key": SETTINGS_PRIVATE_KEY,
                "webhook_secret": "enterprise-secret",
            },
        }
    )
    def test_install_redirects_to_selected_host(self):
        response = self.client.get(
            reverse("github-app-install"),
            {
                "next": reverse("github-app-repositories"),
                "host": "github.example.com",
                "workspace": str(self.workspace.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response["Location"])
        self.assertEqual(parsed.netloc, "github.example.com")
        self.assertEqual(
            parsed.path,
            "/github-apps/weblate-enterprise-app/installations/select_target",
        )

    @patch("weblate.vcs.github.get_app_installation")
    @patch.object(GitHubInstallation, "refresh_repositories")
    def test_setup_connects_installation(self, mock_refresh, mock_get_installation):
        mock_get_installation.return_value = {
            "id": 12345,
            "account": {"login": "test-org", "type": "Organization"},
        }
        install_url = self._start_install(reverse("github-app-repositories"))
        state = parse_qs(urlparse(install_url).query)["state"][0]

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state},
        )

        self.assertRedirects(response, reverse("github-app-repositories"))
        connected = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertEqual(connected.target_login, "test-org")
        mock_refresh.assert_called_once()

    @patch("weblate.vcs.github.get_app_installation")
    @patch.object(GitHubInstallation, "refresh_repositories")
    def test_setup_preserves_url_fragment(self, mock_refresh, mock_get_installation):
        mock_get_installation.return_value = {
            "id": 12345,
            "account": {"login": "test-org", "type": "Organization"},
        }
        # The component-create page builds the install link with a #github
        # fragment so the From GitHub tab is reactivated on return.
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state},
        )

        # fetch_redirect_response=False because the relative URL points at a
        # view requiring extra setup; we only care that the Location is intact.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], next_url)

    def test_repository_list_uses_workspace_scope(self):
        user = create_another_user()
        self.project.add_user(user, "Administration")
        self.client.force_login(user)
        other_project = Project.objects.create(
            name="Other GitHub Project",
            slug="other-github-project",
            web="https://example.com/",
        )
        other_workspace = Workspace.objects.create(name="Other Workspace")
        other_project.workspace = other_workspace
        other_project.save(update_fields=["workspace"])
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[{"full_name": "test-org/repo1"}],
        )
        GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="other-org",
            workspace=other_workspace,
            repositories=[{"full_name": "other-org/repo2"}],
        )

        response = self.client.get(reverse("github-app-repositories"))

        self.assertContains(response, "test-org/repo1")
        self.assertNotContains(response, "other-org/repo2")

    def test_remove_installation(self):
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )

        response = self.client.post(
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk})
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubInstallation.objects.filter(pk=installation.pk).exists())

    def test_remove_installation_rejects_get(self):
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )

        response = self.client.get(
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk})
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(GitHubInstallation.objects.filter(pk=installation.pk).exists())


MANIFEST_RESPONSE = {
    "id": 4242,
    "slug": "weblate-auto",
    "pem": "-----BEGIN RSA PRIVATE KEY-----\nmanifest\n-----END RSA PRIVATE KEY-----",
    "webhook_secret": "fresh-secret",
    "html_url": "https://github.com/apps/weblate-auto",
}


class GitHubAppManifestViewTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.org",
            password="testpwd",
        )
        self.client.force_login(self.user)

    def test_register_renders_editable_form(self):
        response = self.client.get(reverse("github-app-register"))

        self.assertEqual(response.status_code, 200)
        # Editable inputs are present
        self.assertContains(response, 'name="host"')
        self.assertContains(response, 'name="org"')
        self.assertContains(response, 'name="name"')
        # Form posts to the Weblate submit handler, not directly to GitHub
        self.assertContains(
            response, 'action="{}"'.format(reverse("github-app-register-submit"))
        )
        # Manifest preview shown
        self.assertContains(response, "&quot;default_permissions&quot;")
        # Default webhook URL appears (no host query for github.com)
        self.assertEqual(response.context["hostname"], "github.com")
        self.assertNotIn("?host=", response.context["webhook_url"])

    def test_register_submit_form_targets_redirect_endpoint(self):
        response = self._post_register(host="github.example.com")

        self.assertEqual(response.status_code, 200)
        # The intermediate form is same-origin (CSP form-action 'self'); the
        # cross-origin POST to GitHub is achieved via a 307 from Weblate.
        self.assertContains(
            response, 'action="{}"'.format(reverse("github-app-register-redirect"))
        )
        # CSP is not relaxed for the github host
        csp = response["Content-Security-Policy"]
        form_action = next(
            part.strip()
            for part in csp.split(";")
            if part.strip().startswith("form-action")
        )
        self.assertNotIn("github.example.com", form_action)
        # The action URL is stashed in session for the redirect view
        self.assertIn(
            "https://github.example.com/settings/apps/new",
            self.client.session["github_app_register_action_url"],
        )

    def test_register_redirect_returns_307_to_github(self):
        self._post_register(host="github.com", org="acme")
        action_url = self.client.session["github_app_register_action_url"]

        response = self.client.post(
            reverse("github-app-register-redirect"),
            {"manifest": '{"name": "Weblate"}'},
        )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response["Location"], action_url)
        # Session entry is single-use
        self.assertNotIn("github_app_register_action_url", self.client.session)

    def test_register_redirect_without_session_bounces(self):
        response = self.client.post(
            reverse("github-app-register-redirect"),
            {"manifest": '{"name": "Weblate"}'},
        )

        self.assertRedirects(response, reverse("github-app-register"))

    def test_register_redirect_rejects_get(self):
        response = self.client.get(reverse("github-app-register-redirect"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("github-app-register"))

    def test_register_submit_rejects_get(self):
        response = self.client.get(reverse("github-app-register-submit"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("github-app-register"))

    def test_register_form_prefills_query_params(self):
        response = self.client.get(
            reverse("github-app-register"),
            {"host": "github.example.com", "org": "acme", "name": "Custom"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["hostname"], "github.example.com")
        self.assertEqual(response.context["org"], "acme")
        self.assertEqual(response.context["name"], "Custom")
        # GHE webhook URL must carry the host hint
        self.assertIn("?host=github.example.com", response.context["webhook_url"])

    def _post_register(self, **fields):
        return self.client.post(reverse("github-app-register-submit"), fields)

    def _action_url(self) -> str:
        return self.client.session["github_app_register_action_url"]

    def test_register_post_targets_github_com(self):
        response = self._post_register(host="github.com")

        self.assertEqual(response.status_code, 200)
        action_url = self._action_url()
        self.assertIn("https://github.com/settings/apps/new", action_url)
        self.assertIn("state=", action_url)
        # Hidden manifest field that the 307 will re-post to GitHub
        self.assertContains(response, 'name="manifest"')

    def test_register_post_targets_org(self):
        self._post_register(host="github.com", org="acme")

        self.assertIn(
            "https://github.com/organizations/acme/settings/apps/new",
            self._action_url(),
        )

    def test_register_post_targets_enterprise_host(self):
        self._post_register(host="github.example.com")

        self.assertIn(
            "https://github.example.com/settings/apps/new",
            self._action_url(),
        )

    def test_register_post_targets_enterprise_host_and_org(self):
        self._post_register(host="github.example.com", org="acme")

        self.assertIn(
            "https://github.example.com/organizations/acme/settings/apps/new",
            self._action_url(),
        )

    def test_register_post_blank_host_defaults_to_github_com(self):
        self._post_register(host="", org="")

        self.assertIn(
            "https://github.com/settings/apps/new",
            self._action_url(),
        )

    @patch("weblate.vcs.views.exchange_github_app_manifest_code")
    def test_register_callback_stores_credentials(self, mock_exchange):
        mock_exchange.return_value = dict(MANIFEST_RESPONSE)
        # Prime the session state via a POST to the register view
        self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url()).query)["state"][0]

        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "tempcode123", "state": state},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        mock_exchange.assert_called_once_with("tempcode123", "github.com")
        credentials = GitHubAppCredentials.objects.get(hostname="github.com")
        self.assertEqual(credentials.app_id, "4242")
        self.assertEqual(credentials.app_slug, "weblate-auto")
        self.assertEqual(credentials.webhook_secret, "fresh-secret")
        self.assertIn("manifest", credentials.private_key)

    @patch("weblate.vcs.views.exchange_github_app_manifest_code")
    def test_register_callback_updates_existing(self, mock_exchange):
        # Submit first (no row yet) so the submit-time duplicate guard passes.
        mock_exchange.return_value = dict(MANIFEST_RESPONSE)
        self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url()).query)["state"][0]
        # Simulate a concurrent row appearing between submit and callback —
        # the callback should still upsert rather than crash.
        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="1",
            app_slug="old",
            private_key="old-key",
            webhook_secret="old-secret",
        )

        self.client.get(
            reverse("github-app-register-callback"),
            {"code": "tempcode123", "state": state},
        )

        credentials = GitHubAppCredentials.objects.get(hostname="github.com")
        self.assertEqual(credentials.app_slug, "weblate-auto")
        self.assertEqual(GitHubAppCredentials.objects.count(), 1)

    def test_register_callback_rejects_missing_code(self):
        response = self.client.get(reverse("github-app-register-callback"))

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

    def test_register_callback_rejects_bad_state(self):
        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "x", "state": "tampered"},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

    @patch("weblate.vcs.views.exchange_github_app_manifest_code")
    def test_register_callback_rejects_incomplete_response(self, mock_exchange):
        mock_exchange.return_value = {"id": 99}  # missing pem/slug/secret
        self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url()).query)["state"][0]

        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "x", "state": state},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

    def test_register_requires_management_access(self):
        non_admin = User.objects.create_user(
            username="plain",
            email="plain@example.org",
            password="testpwd",
        )
        self.client.force_login(non_admin)

        response = self.client.get(reverse("github-app-register"))

        self.assertEqual(response.status_code, 403)

    def test_register_form_warns_about_existing_host(self):
        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self.client.get(reverse("github-app-register"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["host_already_registered"])
        self.assertEqual(response.context["existing_hosts"], ["github.com"])
        self.assertContains(response, "already registered")
        # Submit button disabled when host conflicts
        self.assertContains(response, "disabled")

    def test_register_submit_blocks_duplicate_host(self):
        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self._post_register(host="github.com")

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertNotIn("github_app_register_action_url", self.client.session)

    def test_register_submit_allows_different_host(self):
        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self._post_register(host="github.example.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "https://github.example.com/settings/apps/new",
            self.client.session["github_app_register_action_url"],
        )

    def test_register_form_defaults_to_public(self):
        response = self.client.get(reverse("github-app-register"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["public"])
        # Checkbox starts checked so the rendered manifest is public.
        self.assertIn('"public": true', response.context["manifest_json"])

    def test_register_post_includes_public_in_session_state_path(self):
        """The submit flow honours the visibility checkbox."""
        # Default: checkbox ticked → public:true in manifest body.
        response = self._post_register(host="github.com", public="1")
        self.assertEqual(response.status_code, 200)
        # Inspect the manifest stored in the hidden submit form field.
        self.assertContains(response, "&quot;public&quot;: true")

    def test_register_post_respects_unchecked_public(self):
        # Unchecked checkboxes are simply absent from POST data.
        response = self._post_register(host="github.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&quot;public&quot;: false")

    def test_register_form_enforces_name_length(self):
        response = self.client.get(reverse("github-app-register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'maxlength="34"')
        self.assertEqual(response.context["name_max_length"], 34)

    def test_register_truncates_long_names(self):
        long_name = "x" * 100
        self._post_register(host="github.com", name=long_name)
        action_url = self.client.session["github_app_register_action_url"]
        # State carries the manifest indirectly; the manifest preview on the
        # editable form uses the same truncation rule, so check via GET too.
        response = self.client.get(reverse("github-app-register"), {"name": long_name})
        self.assertEqual(len(response.context["name"]), 34)
        # Action URL was successfully built — implying GitHub will not reject
        self.assertTrue(action_url.startswith("https://github.com/"))


class GitHubAppCredentialsListPageTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.org",
            password="testpwd",
        )
        self.client.force_login(self.user)

    def test_page_renders_remove_app_modal(self):
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self.client.get(reverse("manage-github-accounts"))

        self.assertEqual(response.status_code, 200)
        # Trigger button references the modal by id.
        self.assertContains(
            response,
            f'data-bs-target="#remove-app-{credentials.pk}"',
        )
        # Modal contains the POST form to the remove endpoint, and no inline
        # confirm() handler is used.
        self.assertContains(
            response,
            f'id="remove-app-{credentials.pk}"',
        )
        self.assertNotContains(response, "onsubmit=")
        self.assertContains(
            response,
            'action="{}"'.format(
                reverse(
                    "manage-github-app-remove",
                    kwargs={"pk": credentials.pk},
                )
            ),
        )

    def test_page_lists_registered_apps(self):
        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
            html_url="https://github.com/apps/weblate-on-com",
        )
        GitHubAppCredentials.objects.create(
            hostname="github.example.com",
            app_id="222",
            app_slug="weblate-on-ghe",
            private_key="pem2",
            webhook_secret="wh2",
        )

        response = self.client.get(reverse("manage-github-accounts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "weblate-on-com")
        self.assertContains(response, "weblate-on-ghe")
        self.assertContains(response, "github.example.com")
        hostnames = [app["hostname"] for app in response.context["apps"]]
        self.assertEqual(hostnames, ["github.com", "github.example.com"])

    def test_remove_app_credentials(self):
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self.client.post(
            reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(
            GitHubAppCredentials.objects.filter(pk=credentials.pk).exists()
        )

    def test_remove_app_rejects_get(self):
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self.client.get(
            reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(GitHubAppCredentials.objects.filter(pk=credentials.pk).exists())
