# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlencode, urlparse

import responses
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.models import Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.site import get_site_url
from weblate.vcs.github import (
    GITHUB_APP_MANIFEST_EVENTS,
    GITHUB_APP_MANIFEST_PERMISSIONS,
    GitHubAppCredentials,
    GitHubInstallation,
)
from weblate.vcs.tests.utils import generate_private_key
from weblate.workspaces.models import Workspace

SETTINGS_PRIVATE_KEY = generate_private_key()


def _repo_entry(full_name: str, **overrides) -> dict:
    """Build a cached repository entry matching the GitHub API shape."""
    entry = {
        "name": full_name.rsplit("/", 1)[-1],
        "full_name": full_name,
        "clone_url": f"https://github.com/{full_name}.git",
        "ssh_url": f"git@github.com:{full_name}.git",
        "html_url": f"https://github.com/{full_name}",
        "default_branch": "main",
        "private": False,
        "description": "",
    }
    entry.update(overrides)
    return entry


def _import_url(repo: dict, **overrides) -> str:
    params = {
        "repo": repo["clone_url"],
        "branch": repo["default_branch"],
        "vcs": "github-app",
        "name": repo["name"],
        "slug": repo["name"],
    }
    params.update(overrides)
    return f"{reverse('create-component-vcs')}?{urlencode(params)}"


class GitHubInstallationViewTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.user.is_superuser = True
        self.user.save()

        self.workspace = Workspace.objects.create(name="Test Workspace")
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])

        self._make_credentials()

    def _make_credentials(
        self, hostname: str = "github.com", **overrides
    ) -> GitHubAppCredentials:
        defaults = {
            "app_id": "99999",
            "app_slug": "weblate-app",
            "private_key": SETTINGS_PRIVATE_KEY,
            "webhook_secret": "secret",
            "client_id": "Iv1.testclientid",
            "client_secret": "client-secret",
        }
        defaults.update(overrides)
        return GitHubAppCredentials.objects.create(hostname=hostname, **defaults)

    def _mock_oauth(
        self,
        *,
        hostname: str = "github.com",
        accessible_ids: tuple[str, ...] = ("12345",),
        token: str = "ghu_user",  # noqa: S107
    ) -> None:
        """Mock the install-time user-authorization (OAuth) verification."""
        oauth_base = (
            "https://github.com" if hostname == "github.com" else f"https://{hostname}"
        )
        api_base = (
            "https://api.github.com"
            if hostname == "github.com"
            else f"https://{hostname}/api/v3"
        )
        responses.add(
            responses.POST,
            f"{oauth_base}/login/oauth/access_token",
            json={"access_token": token, "token_type": "bearer"},
        )
        responses.add(
            responses.GET,
            f"{api_base}/user/installations?per_page=100",
            json={"installations": [{"id": int(i)} for i in accessible_ids]},
        )

    def _mock_setup_api(
        self,
        *,
        repositories: list[dict] | None = None,
    ) -> list[dict]:
        if repositories is None:
            repositories = [_repo_entry("test-org/repo1")]
        responses.add(
            responses.GET,
            "https://api.github.com/app/installations/12345",
            json={
                "id": 12345,
                "account": {"login": "test-org", "type": "Organization"},
            },
        )
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        responses.add(
            responses.GET,
            "https://api.github.com/installation/repositories?per_page=100",
            json={"repositories": repositories},
        )
        return repositories

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

    def test_management_overview_uses_single_workspace_for_install_link(self):
        response = self.client.get(reverse("manage-github-accounts"))

        params = urlencode(
            {
                "next": reverse("manage-github-accounts"),
                "workspace": self.workspace.pk,
            }
        )
        install_url = f"{reverse('github-app-install')}?{params}"
        self.assertContains(response, install_url.replace("&", "&amp;"))

    def test_account_vcs_integrations_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("account-vcs"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_profile_links_account_vcs_integrations(self):
        response = self.client.get(reverse("profile"))

        self.assertContains(response, reverse("account-vcs"))
        self.assertContains(response, "Manage VCS integrations")

    def test_account_vcs_integrations_uses_workspace_scope(self):
        user = self.anotheruser
        self.project.add_user(user, "Administration")
        other_workspace = Workspace.objects.create(name="Other Workspace")
        other_project = Project.objects.create(
            name="Other GitHub Project",
            slug="other-github-project",
            web="https://example.com/",
            workspace=other_workspace,
        )
        other_project.add_user(user, "Administration")
        hidden_workspace = Workspace.objects.create(name="Hidden Workspace")
        hidden_project = Project.objects.create(
            name="Hidden GitHub Project",
            slug="hidden-github-project",
            web="https://example.com/",
            workspace=hidden_workspace,
        )
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1")],
        )
        GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="hidden-org",
            workspace=hidden_project.workspace,
            repositories=[_repo_entry("hidden-org/repo2")],
        )
        self.client.login(username=user.username, password="testpassword")

        response = self.client.get(reverse("account-vcs"))

        self.assertContains(response, "test-org")
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, other_workspace.name)
        self.assertNotContains(response, "hidden-org")
        self.assertContains(
            response,
            reverse("manage-github-account-refresh", kwargs={"pk": installation.pk}),
        )
        self.assertContains(
            response,
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )
        for workspace in (self.workspace, other_workspace):
            install_url = (
                f"{reverse('github-app-install')}?"
                f"{urlencode({'next': reverse('account-vcs'), 'host': 'github.com', 'workspace': workspace.pk})}"
            )
            self.assertContains(response, install_url.replace("&", "&amp;"))

    def test_account_vcs_integrations_filters_selected_workspace(self):
        user = self.anotheruser
        self.project.add_user(user, "Administration")
        other_workspace = Workspace.objects.create(name="Other Workspace")
        other_project = Project.objects.create(
            name="Other GitHub Project",
            slug="other-github-project",
            web="https://example.com/",
            workspace=other_workspace,
        )
        other_project.add_user(user, "Administration")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1")],
        )
        GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="other-org",
            workspace=other_workspace,
            repositories=[_repo_entry("other-org/repo2")],
        )
        self.client.login(username=user.username, password="testpassword")

        response = self.client.get(
            reverse("account-vcs"), {"workspace": str(self.workspace.pk)}
        )

        self.assertEqual(response.context["selected_workspace"], self.workspace)
        self.assertContains(response, "test-org")
        self.assertContains(response, self.workspace.name)
        self.assertNotContains(response, "other-org")
        self.assertNotContains(response, other_workspace.name)
        next_url = f"{reverse('account-vcs')}?workspace={self.workspace.pk}"
        install_url = (
            f"{reverse('github-app-install')}?"
            f"{urlencode({'next': next_url, 'host': 'github.com', 'workspace': self.workspace.pk})}"
        )
        self.assertContains(response, install_url.replace("&", "&amp;"))

    def test_account_vcs_integrations_accepts_workspace_owner(self):
        owner = User.objects.create_user(
            username="workspace owner",
            email="workspaceowner@example.org",
            password="testpassword",
        )
        self.workspace.add_owner(owner)
        self.client.login(username=owner.username, password="testpassword")

        response = self.client.get(
            reverse("account-vcs"), {"workspace": str(self.workspace.pk)}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_workspace"], self.workspace)
        self.assertContains(response, "Connect GitHub account")

    def test_account_vcs_integrations_shows_unregistered_apps(self):
        GitHubInstallation.objects.create(
            hostname="github.example.com",
            installation_id="12345",
            target_type="Organization",
            target_login="stale-org",
            workspace=self.workspace,
            repositories=[_repo_entry("stale-org/repo1")],
        )

        response = self.client.get(reverse("account-vcs"))

        self.assertContains(response, "github.example.com")
        self.assertContains(response, "stale-org")
        self.assertContains(response, "Not registered")

    def test_install_requires_host_selection_with_multiple_configs(self):
        self._make_credentials(
            hostname="github.example.com",
            app_id="11111",
            app_slug="weblate-enterprise-app",
            webhook_secret="enterprise-secret",
        )
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

    @responses.activate
    def test_setup_connects_installation(self):
        repositories = [_repo_entry("test-org/repo1", default_branch="stable")]
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(accessible_ids=("12345",))
        self._mock_setup_api(repositories=repositories)
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )

        self.assertRedirects(response, next_url)
        connected = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertEqual(connected.target_login, "test-org")
        self.assertEqual(connected.target_type, "Organization")
        self.assertEqual(connected.repositories, repositories)
        self.assertIsNotNone(connected.repositories_updated)
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
                ("GET", "https://api.github.com/app/installations/12345"),
                (
                    "POST",
                    "https://api.github.com/app/installations/12345/access_tokens",
                ),
                (
                    "GET",
                    "https://api.github.com/installation/repositories?per_page=100",
                ),
            ],
        )

    def test_setup_rejects_missing_oauth_code(self):
        # Without the install-time OAuth code there is nothing proving the user
        # controls the installation, so the connection is refused outright.
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )

    @responses.activate
    def test_setup_rejects_foreign_installation_id(self):
        # The attacker holds a valid signed state for their own workspace and a
        # valid OAuth code for *their* GitHub account, then swaps in another
        # account's installation ID (67890). ``GET /user/installations`` only
        # lists 12345, so 67890 must not be connected nor have a token minted.
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(accessible_ids=("12345",))
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "67890", "state": state, "code": "oauth-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="67890").exists()
        )
        # Ownership is rejected before any App-level token is minted: only the
        # OAuth exchange and the user-installations lookup are called.
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
            ],
        )

    @responses.activate
    def test_setup_rejects_when_code_exchange_fails(self):
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        responses.add(
            responses.POST,
            "https://github.com/login/oauth/access_token",
            json={"error": "bad_verification_code"},
        )
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "stale-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )

    def test_repository_list_uses_workspace_scope(self):
        user = self.anotheruser
        self.project.add_user(user, "Administration")
        self.client.login(username=user.username, password="testpassword")
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
            repositories=[_repo_entry("test-org/repo1")],
        )
        GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="other-org",
            workspace=other_workspace,
            repositories=[_repo_entry("other-org/repo2")],
        )

        response = self.client.get(reverse("github-app-repositories"))

        self.assertContains(response, "test-org/repo1")
        self.assertNotContains(response, "other-org/repo2")

    def test_repository_list_hides_hosts_without_credentials(self):
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1")],
        )
        GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="stale-org",
            hostname="github.example.com",
            workspace=self.workspace,
            repositories=[
                _repo_entry(
                    "stale-org/repo2",
                    clone_url="https://github.example.com/stale-org/repo2.git",
                    html_url="https://github.example.com/stale-org/repo2",
                    ssh_url="git@github.example.com:stale-org/repo2.git",
                )
            ],
        )

        response = self.client.get(reverse("github-app-repositories"))

        self.assertContains(response, "test-org/repo1")
        self.assertNotContains(response, "stale-org/repo2")

    def test_repository_import_link_preselects_github_app_vcs(self):
        repo = _repo_entry("test-org/repo1", default_branch="stable")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )

        response = self.client.get(reverse("github-app-repositories"))

        self.assertNotContains(response, "test-org (github.com/12345)")
        import_path = _import_url(repo)
        self.assertEqual(
            response.context["repositories"][0]["import_url"],
            import_path,
        )
        self.assertContains(response, import_path.replace("&", "&amp;"))

    def test_repository_list_omits_archived_repositories(self):
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[
                _repo_entry("test-org/active"),
                _repo_entry("test-org/archived", archived=True),
            ],
        )

        response = self.client.get(reverse("github-app-repositories"))

        self.assertContains(response, "test-org/active")
        self.assertNotContains(response, "test-org/archived")

    @responses.activate
    def test_refresh_repositories_updates_installation(self):
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        repo = _repo_entry("test-org/repo1", default_branch="stable")

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
                    repo,
                    _repo_entry("test-org/archived", archived=True),
                ]
            },
        )
        response = self.client.post(
            reverse("manage-github-account-refresh", kwargs={"pk": installation.pk}),
            {"next": reverse("github-app-repositories")},
        )

        self.assertRedirects(response, reverse("github-app-repositories"))
        installation.refresh_from_db()
        self.assertEqual(installation.repositories, [repo])
        self.assertIsNotNone(installation.repositories_updated)
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                (
                    "POST",
                    "https://api.github.com/app/installations/12345/access_tokens",
                ),
                (
                    "GET",
                    "https://api.github.com/installation/repositories?per_page=100",
                ),
            ],
        )

    def test_refresh_repositories_rejects_get(self):
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )

        response = self.client.get(
            reverse("manage-github-account-refresh", kwargs={"pk": installation.pk})
        )

        self.assertEqual(response.status_code, 405)

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


class GitHubAppAccessControlTest(ViewTestCase):
    """Permission checks for the GitHub App connect/import views."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()

        self.workspace = Workspace.objects.create(name="ACL Workspace")
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])

        GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="99999",
            app_slug="weblate-app",
            private_key=SETTINGS_PRIVATE_KEY,
            webhook_secret="secret",
            client_id="Iv1.testclientid",
            client_secret="client-secret",
        )

        self.user = User.objects.create_user(
            username="main user",
            email="mainuser@example.org",
            password="testpassword",
        )
        self.project.add_user(self.user, "Administration")

        self.other_user = User.objects.create_user(
            username="other user",
            email="otheruser@example.org",
            password="testpassword",
        )

    def _mock_setup_api(self, repositories: list[dict]) -> None:
        responses.add(
            responses.POST,
            "https://github.com/login/oauth/access_token",
            json={"access_token": "ghu_user", "token_type": "bearer"},
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user/installations?per_page=100",
            json={"installations": [{"id": 12345}]},
        )
        responses.add(
            responses.GET,
            "https://api.github.com/app/installations/12345",
            json={
                "id": 12345,
                "account": {"login": "test-org", "type": "Organization"},
            },
        )
        responses.add(
            responses.POST,
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        responses.add(
            responses.GET,
            "https://api.github.com/installation/repositories?per_page=100",
            json={"repositories": repositories},
        )

    def _start_install(self, user: User) -> str:
        """Run the install entry point as ``user`` and return the signed state."""
        self.client.login(username=user.username, password="testpassword")
        location = self.client.get(
            reverse("github-app-install"),
            {
                "workspace": str(self.workspace.pk),
                "next": reverse("github-app-repositories"),
            },
        )["Location"]
        return parse_qs(urlparse(location).query)["state"][0]

    def test_install_requires_login(self):
        self.client.logout()
        response = self.client.get(
            reverse("github-app-install"),
            {"workspace": str(self.workspace.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_setup_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("github-app-setup"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_setup_denied_for_user_managing_a_different_workspace(self):
        # A valid signed state for ``self.workspace`` produced by its admin.
        state = self._start_install(self.user)

        # A user who manages an unrelated workspace must not be able to bind
        # GitHub to a workspace they don't manage.
        other_workspace = Workspace.objects.create(name="Other ACL Workspace")
        other_project = self.create_project(
            name="Other ACL", slug="other-acl", workspace=other_workspace
        )
        other_project.add_user(self.other_user, "Administration")
        self.client.login(username=self.other_user.username, password="testpassword")

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )

    @responses.activate
    def test_workspace_member_can_import_repo_linked_by_other_user(self):
        repo = _repo_entry("test-org/repo1", default_branch="stable")

        # User A links the GitHub account to the shared workspace.
        state = self._start_install(self.user)
        self._mock_setup_api([repo])
        setup = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )
        self.assertRedirects(setup, reverse("github-app-repositories"))
        installation = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertEqual(installation.target_login, "test-org")

        self.client.login(username=self.other_user.username, password="testpassword")
        response = self.client.get(
            reverse("github-app-install"),
            {"workspace": str(self.workspace.pk)},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse("github-app-repositories"))
        self.assertEqual(response.status_code, 403)

        # user added to project admin and can import repo now
        self.project.add_user(self.other_user, "Administration")
        response = self.client.get(reverse("github-app-repositories"))
        self.assertContains(response, "test-org/repo1")
        import_path = _import_url(repo)
        self.assertEqual(
            response.context["repositories"][0]["import_url"],
            import_path,
        )
        self.assertContains(response, import_path.replace("&", "&amp;"))
        create = self.client.get(import_path)
        self.assertEqual(create.status_code, 200)


MANIFEST_RESPONSE = {
    "id": 4242,
    "slug": "weblate-auto",
    "pem": "-----BEGIN RSA PRIVATE KEY-----\nmanifest\n-----END RSA PRIVATE KEY-----",
    "webhook_secret": "fresh-secret",
    "client_id": "Iv1.manifestclientid",
    "client_secret": "manifest-client-secret",
    "html_url": "https://github.com/apps/weblate-auto",
}


class GitHubAppManifestViewTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_superuser(
            username="admin",
            email="admin@example.org",
            password="testpassword",
        )
        self.client.login(username="admin", password="testpassword")

    def _post_register(self, **fields):
        return self.client.post(reverse("github-app-register-submit"), fields)

    def _action_url(self) -> str:
        return self.client.session["github_app_register_action_url"]

    def _capture_github_call(self, **fields) -> tuple[str, dict]:
        submit = self._post_register(**fields)
        self.assertEqual(submit.status_code, 200)
        manifest_json = submit.context["manifest_json"]
        redirect = self.client.post(
            reverse("github-app-register-redirect"),
            {"manifest": manifest_json},
        )
        self.assertEqual(redirect.status_code, 307)
        return redirect["Location"], json.loads(manifest_json)

    def test_register_post_sends_expected_manifest_to_github(self):
        url, manifest = self._capture_github_call(
            host="github.com", name="My Weblate", public="1"
        )

        # Destination of the cross-origin POST GitHub receives.
        self.assertTrue(url.startswith("https://github.com/settings/apps/new?"))
        self.assertIn("state", parse_qs(urlparse(url).query))

        # Body parameters GitHub uses to create the App.
        self.assertEqual(manifest["name"], "My Weblate")
        self.assertEqual(manifest["url"], get_site_url())
        # The webhook carries an opaque per-integration token, so assert its
        # shape rather than the (randomly generated) token value.
        hook = manifest["hook_attributes"]
        self.assertTrue(hook["active"])
        self.assertTrue(hook["url"].startswith(get_site_url("/hooks/integrations/")))
        token = urlparse(hook["url"]).path.rstrip("/").rsplit("/", 1)[1]
        self.assertEqual(
            hook["url"],
            get_site_url(
                reverse("integration-webhook", kwargs={"integration_token": token})
            ),
        )
        self.assertEqual(
            manifest["redirect_url"],
            get_site_url(reverse("github-app-register-callback")),
        )
        self.assertEqual(
            manifest["setup_url"], get_site_url(reverse("github-app-setup"))
        )
        self.assertEqual(
            manifest["callback_urls"], [get_site_url(reverse("github-app-setup"))]
        )
        self.assertTrue(manifest["setup_on_update"])
        self.assertTrue(manifest["request_oauth_on_install"])
        self.assertTrue(manifest["public"])
        self.assertEqual(
            manifest["default_permissions"], dict(GITHUB_APP_MANIFEST_PERMISSIONS)
        )
        self.assertEqual(manifest["default_events"], list(GITHUB_APP_MANIFEST_EVENTS))

        url, _manifest = self._capture_github_call(host="github.example.com")

        parsed = urlparse(url)
        self.assertEqual(parsed.netloc, "github.example.com")
        self.assertEqual(parsed.path, "/settings/apps/new")

        url, _manifest = self._capture_github_call(
            host="github.example.com", org="acme"
        )

        parsed = urlparse(url)
        self.assertEqual(parsed.netloc, "github.example.com")
        self.assertEqual(parsed.path, "/organizations/acme/settings/apps/new")

    @responses.activate
    def test_register_callback_stores_credentials(self):
        responses.add(
            responses.POST,
            "https://api.github.com/app-manifests/tempcode123/conversions",
            json=MANIFEST_RESPONSE,
        )
        # Prime the session state via a POST to the register view
        self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url()).query)["state"][0]

        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "tempcode123", "state": state},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(
            responses.calls[0].request.url,
            "https://api.github.com/app-manifests/tempcode123/conversions",
        )
        credentials = GitHubAppCredentials.objects.get(hostname="github.com")
        self.assertEqual(credentials.app_id, "4242")
        self.assertEqual(credentials.app_slug, "weblate-auto")
        self.assertEqual(credentials.webhook_secret, "fresh-secret")
        self.assertEqual(credentials.client_id, "Iv1.manifestclientid")
        self.assertEqual(credentials.client_secret, "manifest-client-secret")
        self.assertIn("manifest", credentials.private_key)

    @responses.activate
    def test_register_callback_updates_existing(self):
        responses.add(
            responses.POST,
            "https://api.github.com/app-manifests/tempcode123/conversions",
            json=MANIFEST_RESPONSE,
        )
        self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url()).query)["state"][0]
        # Simulate a concurrent row appearing between submit and callback -
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

    @responses.activate
    def test_register_callback_reject(self):
        response = self.client.get(reverse("github-app-register-callback"))

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "x", "state": "tampered"},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

        responses.add(
            responses.POST,
            "https://api.github.com/app-manifests/x/conversions",
            json={"id": 99},  # missing pem/slug/secret
        )
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
            password="testpassword",
        )
        self.client.login(username=non_admin.username, password="testpassword")

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

        response = self._post_register(host="github.com")
        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertNotIn("github_app_register_action_url", self.client.session)

        url, _manifest = self._capture_github_call(host="github.example.com")

        parsed = urlparse(url)
        self.assertEqual(parsed.netloc, "github.example.com")
        self.assertEqual(parsed.path, "/settings/apps/new")

    def test_register_truncates_long_names(self):
        long_name = "x" * 100
        _url, manifest = self._capture_github_call(host="github.com", name=long_name)
        # GitHub rejects names longer than 34 chars, so the manifest body must
        # already be truncated to the limit.
        self.assertEqual(manifest["name"], "x" * 34)

    def test_credentials_page_renders_remove_app_modal(self):
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self.client.get(reverse("manage-github-accounts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'data-bs-target="#remove-app-{credentials.pk}"',
        )
        self.assertContains(
            response,
            f'id="remove-app-{credentials.pk}"',
        )
        self.assertNotContains(response, "onsubmit=")
        self.assertContains(
            response,
            f'action="{reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})}"',
        )

    def test_credentials_page_lists_registered_apps(self):
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

    def test_credentials_remove_app_credentials(self):
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

        response = self.client.post(
            reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(
            GitHubAppCredentials.objects.filter(pk=credentials.pk).exists()
        )
