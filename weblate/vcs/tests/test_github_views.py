# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import cast
from urllib.parse import parse_qs, urlencode, urlparse

import responses
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from weblate.auth.models import Group, Permission, Role, User
from weblate.trans.models import Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.site import get_site_url
from weblate.vcs.github import (
    GITHUB_APP_MANIFEST_EVENTS,
    GITHUB_APP_MANIFEST_PERMISSIONS,
    GitHubAppCredentials,
    GitHubInstallation,
)
from weblate.vcs.models import InstallationProvider, PendingInstallation
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


def _import_url(installation: GitHubInstallation, repo: dict, **overrides) -> str:
    params = {}
    params.update(overrides)
    url = reverse(
        "github-app-repository-import",
        kwargs={"pk": installation.pk, "repo_full_name": repo["full_name"]},
    )
    if params:
        return f"{url}?{urlencode(params)}"
    return url


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

    def _grant_management_permission(self, user: User) -> None:
        role = Role.objects.create(name=f"GitHub management {user.pk}")
        role.permissions.add(Permission.objects.get(codename="management.use"))
        group = Group.objects.create(name=f"GitHub management {user.pk}")
        group.roles.add(role)
        user.groups.add(group)
        user.clear_cache()

    def _mock_oauth(
        self,
        *,
        hostname: str = "github.com",
        accessible_ids: tuple[str, ...] = ("12345",),
        managed_installation_ids: tuple[str, ...] | None = None,
        installations: list[dict] | None = None,
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
        installation_rows = (
            installations
            if installations is not None
            else [
                {
                    "id": int(i),
                    "account": {"login": "test-org", "type": "Organization"},
                }
                for i in accessible_ids
            ]
        )
        responses.add(
            responses.GET,
            f"{api_base}/user/installations?per_page=100",
            json={"installations": installation_rows},
        )
        if managed_installation_ids is None:
            managed_installation_ids = tuple(
                str(installation.get("id")) for installation in installation_rows
            )
        managed_ids = set(managed_installation_ids)
        org_rows: dict[str, list[dict]] = {}
        for installation in installation_rows:
            account: dict[str, str] = (
                cast("dict[str, str]", installation.get("account")) or {}
            )
            if account.get("type") != "Organization":
                continue
            login = account.get("login")
            if not login:
                continue
            rows = org_rows.setdefault(str(login), [])
            if str(installation.get("id")) in managed_ids:
                rows.append(installation)
        for org, rows in org_rows.items():
            responses.add(
                responses.GET,
                f"{api_base}/orgs/{org}/installations?per_page=100",
                json={"installations": rows},
            )

    def _mock_setup_api(
        self,
        *,
        repositories: list[dict] | None = None,
        account: dict | None = None,
    ) -> list[dict]:
        if repositories is None:
            repositories = [_repo_entry("test-org/repo1")]
        if account is None:
            account = {"login": "test-org", "type": "Organization"}
        responses.add(
            responses.GET,
            "https://api.github.com/app/installations/12345",
            json={"id": 12345, "account": account},
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

    def assert_installation_remove_modal(
        self, response, installation: GitHubInstallation
    ) -> None:
        self.assertContains(
            response,
            f'data-bs-target="#remove-github-account-{installation.pk}"',
        )
        self.assertContains(
            response,
            f'id="remove-github-account-{installation.pk}"',
        )
        self.assertContains(response, "Remove connected GitHub account?")
        self.assertContains(
            response,
            f'action="{reverse("manage-github-account-remove", kwargs={"pk": installation.pk})}"',
        )
        html = response.content.decode()
        action = f'action="{reverse("manage-github-account-remove", kwargs={"pk": installation.pk})}"'
        form_start = html.index(action)
        form_end = html.index("</form>", form_start)
        self.assertIn('name="csrfmiddlewaretoken"', html[form_start:form_end])
        self.assertNotContains(response, "onsubmit=")

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
        self.workspace.add_owner(user)
        other_workspace = Workspace.objects.create(name="Other Workspace")
        Project.objects.create(
            name="Other GitHub Project",
            slug="other-github-project",
            web="https://example.com/",
            workspace=other_workspace,
        )
        other_workspace.add_owner(user)
        hidden_workspace = Workspace.objects.create(name="Hidden Workspace")
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
            workspace=hidden_workspace,
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
        self.assert_installation_remove_modal(response, installation)
        for workspace in (self.workspace, other_workspace):
            install_url = (
                f"{reverse('github-app-install')}?"
                f"{urlencode({'next': reverse('account-vcs'), 'host': 'github.com', 'workspace': workspace.pk})}"
            )
            self.assertContains(response, install_url.replace("&", "&amp;"))

    def test_project_admin_cannot_manage_account_vcs_integrations(self):
        user = self.anotheruser
        self.project.add_user(user, "Administration")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1")],
        )
        self.client.login(username=user.username, password="testpassword")

        response = self.client.get(reverse("account-vcs"))

        self.assertContains(response, "test-org")
        self.assertContains(response, self.workspace.name)
        self.assertContains(
            response,
            f"{reverse('github-app-repositories')}?workspace={self.workspace.pk}",
        )
        install_url = (
            f"{reverse('github-app-install')}?"
            f"{urlencode({'next': reverse('account-vcs'), 'host': 'github.com', 'workspace': self.workspace.pk})}"
        )
        self.assertNotContains(response, install_url.replace("&", "&amp;"))
        self.assertNotContains(response, "Connect GitHub account")
        self.assertNotContains(
            response,
            reverse("manage-github-account-refresh", kwargs={"pk": installation.pk}),
        )
        self.assertNotContains(
            response,
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )

        install_response = self.client.get(
            reverse("github-app-install"),
            {
                "next": reverse("account-vcs"),
                "host": "github.com",
                "workspace": str(self.workspace.pk),
            },
        )
        self.assertEqual(install_response.status_code, 403)

    def test_project_admin_cannot_manage_github_installation(self):
        user = self.anotheruser
        self.project.add_user(user, "Administration")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1")],
        )
        self.client.login(username=user.username, password="testpassword")

        detail_response = self.client.get(
            reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
        )
        self.assertEqual(detail_response.status_code, 403)
        for view_name in (
            "manage-github-account-refresh",
            "manage-github-account-remove",
        ):
            response = self.client.post(
                reverse(view_name, kwargs={"pk": installation.pk})
            )
            self.assertEqual(response.status_code, 403)
        self.assertTrue(GitHubInstallation.objects.filter(pk=installation.pk).exists())

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
        self.assertNotContains(response, install_url.replace("&", "&amp;"))

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
                (
                    "GET",
                    "https://api.github.com/orgs/test-org/installations?per_page=100",
                ),
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

    @responses.activate
    def test_setup_connects_personal_installation_for_account_owner(self):
        repositories = [_repo_entry("octocat/repo1", default_branch="stable")]
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(
            installations=[
                {"id": 12345, "account": {"login": "octocat", "type": "User"}}
            ]
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "octocat"},
        )
        self._mock_setup_api(
            repositories=repositories,
            account={"login": "octocat", "type": "User"},
        )
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )

        self.assertRedirects(response, next_url)
        connected = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertEqual(connected.target_login, "octocat")
        self.assertEqual(connected.target_type, "User")
        self.assertEqual(connected.repositories, repositories)
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
                ("GET", "https://api.github.com/user"),
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

    @responses.activate
    def test_setup_persists_pending_installation_when_api_not_ready(self):
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(
            installations=[
                {
                    "id": 12345,
                    "account": {"login": "test-org", "type": "Organization"},
                }
            ]
        )
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )

        self.assertRedirects(response, next_url)
        connected = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertTrue(connected.enabled)
        self.assertEqual(connected.target_login, "test-org")
        self.assertEqual(connected.target_type, "Organization")
        self.assertEqual(connected.repositories, [])

    @responses.activate
    def test_setup_applies_pending_installation_webhook(self):
        repositories = [_repo_entry("test-org/repo1", default_branch="stable")]
        PendingInstallation.objects.create(
            provider=InstallationProvider.GITHUB,
            hostname="github.com",
            installation_id="12345",
            payload={
                "action": "created",
                "installation": {
                    "id": 12345,
                    "app_id": 99999,
                    "account": {"login": "test-org", "type": "Organization"},
                },
                "repositories": repositories,
            },
        )
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(accessible_ids=("12345",))
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
        self.assertFalse(
            PendingInstallation.objects.filter(
                provider=InstallationProvider.GITHUB,
                hostname="github.com",
                installation_id="12345",
            ).exists()
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
    def test_setup_rejects_personal_installation_for_non_owner(self):
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(
            installations=[
                {"id": 12345, "account": {"login": "octocat", "type": "User"}}
            ]
        )
        responses.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "repo-collaborator"},
        )
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
                ("GET", "https://api.github.com/user"),
            ],
        )

    @responses.activate
    def test_setup_rejects_org_installation_without_admin_access(self):
        # ``GET /user/installations`` can list organization installations where
        # the user merely has repository access. Weblate must require the
        # stronger organization-admin installation list before connecting it.
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(accessible_ids=("12345",), managed_installation_ids=())
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )
        self.assertEqual(
            [(call.request.method, call.request.url) for call in responses.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
                (
                    "GET",
                    "https://api.github.com/orgs/test-org/installations?per_page=100",
                ),
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

    def test_installation_detail_hides_import_link_when_disabled(self):
        repo = _repo_entry("test-org/repo1")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            enabled=False,
            repositories=[repo],
        )

        response = self.client.get(
            reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
        )

        self.assertContains(response, "test-org/repo1")
        self.assertNotIn("import_url", response.context["repositories"][0])
        self.assertNotContains(response, _import_url(installation, repo))
        self.assertContains(response, "Unavailable")
        self.assert_installation_remove_modal(response, installation)

    def test_installation_detail_hides_import_link_without_credentials(self):
        repo = _repo_entry(
            "stale-org/repo2",
            clone_url="https://github.example.com/stale-org/repo2.git",
            html_url="https://github.example.com/stale-org/repo2",
            ssh_url="git@github.example.com:stale-org/repo2.git",
        )
        installation = GitHubInstallation.objects.create(
            installation_id="67890",
            target_type="Organization",
            target_login="stale-org",
            hostname="github.example.com",
            workspace=self.workspace,
            repositories=[repo],
        )

        response = self.client.get(
            reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
        )

        self.assertContains(response, "stale-org/repo2")
        self.assertNotIn("import_url", response.context["repositories"][0])
        self.assertNotContains(response, _import_url(installation, repo))
        self.assertContains(response, "Unavailable")

    def test_site_manager_can_import_from_installation_detail(self):
        manager = User.objects.create_user(
            username="site manager",
            email="sitemanager@example.org",
            password="testpassword",
        )
        self._grant_management_permission(manager)
        repo = _repo_entry("test-org/repo1")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )
        self.client.login(username=manager.username, password="testpassword")

        response = self.client.get(
            reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
        )

        import_path = _import_url(installation, repo)
        self.assertContains(response, import_path)
        response = self.client.get(import_path)
        self.assertRedirects(
            response,
            f"{reverse('create-component-vcs')}?session_component=1",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session["session_component"]["repo"], repo["clone_url"]
        )

    def test_repository_import_link_preselects_github_app_vcs(self):
        repo = _repo_entry("test-org/repo1", default_branch="stable")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )

        response = self.client.get(reverse("github-app-repositories"))

        self.assertNotContains(response, "test-org (github.com/12345)")
        import_path = _import_url(installation, repo)
        self.assertEqual(
            response.context["repositories"][0]["import_url"],
            import_path,
        )
        self.assertContains(response, import_path.replace("&", "&amp;"))
        self.assert_installation_remove_modal(response, installation)

    def test_repository_import_uses_create_session(self):
        repo = _repo_entry("test-org/repo1", default_branch="stable")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )

        response = self.client.get(
            _import_url(installation, repo, project=self.project.pk)
        )

        self.assertRedirects(
            response,
            f"{reverse('create-component-vcs')}?session_component=1",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session["session_component"],
            {
                "repo": repo["clone_url"],
                "branch": "stable",
                "vcs": "github-app",
                "name": repo["name"],
                "slug": repo["name"],
                "integration_import_vcs": "github-app",
                "project": self.project.pk,
            },
        )

        response = self.client.get(
            f"{reverse('create-component-vcs')}?session_component=1"
        )
        form = response.context["form"]
        self.assertEqual(form["vcs"].value(), "github-app")
        self.assertTrue(form.fields["vcs"].disabled)
        self.assertIn("github-app", dict(form.fields["vcs"].choices))
        self.assertEqual(form["repo"].value(), repo["clone_url"])
        self.assertTrue(form.fields["repo"].disabled)

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
        self.workspace.add_owner(self.user)
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
            json={
                "installations": [
                    {
                        "id": 12345,
                        "account": {"login": "test-org", "type": "Organization"},
                    }
                ]
            },
        )
        responses.add(
            responses.GET,
            "https://api.github.com/orgs/test-org/installations?per_page=100",
            json={
                "installations": [
                    {
                        "id": 12345,
                        "account": {"login": "test-org", "type": "Organization"},
                    }
                ]
            },
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

        # A user who owns an unrelated workspace must not be able to bind
        # GitHub to a workspace they don't manage.
        other_workspace = Workspace.objects.create(name="Other ACL Workspace")
        self.create_project(
            name="Other ACL", slug="other-acl", workspace=other_workspace
        )
        other_workspace.add_owner(self.other_user)
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
        import_path = _import_url(installation, repo)
        self.assertEqual(
            response.context["repositories"][0]["import_url"],
            import_path,
        )
        self.assertContains(response, import_path.replace("&", "&amp;"))
        create = self.client.get(import_path)
        self.assertRedirects(
            create,
            f"{reverse('create-component-vcs')}?session_component=1",
            fetch_redirect_response=False,
        )


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

    def _grant_global_permissions(self, user: User, *permissions: str) -> None:
        role, _created = Role.objects.get_or_create(name="Test GitHub App role")
        permission_objects = list(Permission.objects.filter(codename__in=permissions))
        self.assertEqual(
            {permission.codename for permission in permission_objects},
            set(permissions),
        )
        role.permissions.add(*permission_objects)
        group, _created = Group.objects.get_or_create(name="Test GitHub App team")
        group.roles.add(role)
        user.groups.add(group)
        user.clear_cache()

    def _post_register(self, **fields):
        data = {"host": "github.com", "name": "Test Weblate", "public": "1"}
        data.update(fields)
        return self.client.post(reverse("github-app-register-submit"), data)

    def _action_url(self, response) -> str:
        return response.context["action_url"]

    def _capture_github_call(self, **fields) -> tuple[str, dict]:
        submit = self._post_register(**fields)
        self.assertEqual(submit.status_code, 200)
        manifest_json = submit.context["manifest_json"]
        return self._action_url(submit), json.loads(manifest_json)

    def _get_form_action_csp(self, response) -> str:
        for directive in response["Content-Security-Policy"].split(";"):
            directive = directive.strip()
            if directive.startswith("form-action "):
                return directive
        msg = "Missing form-action directive"
        raise AssertionError(msg)

    def test_register_submit_posts_directly_to_github_with_csp(self):
        for host in ("github.com", "github.example.com", "github"):
            with self.subTest(host=host):
                response = self._post_register(host=host)
                self.assertEqual(response.status_code, 200)
                action_url = self._action_url(response)

                parsed = urlparse(action_url)
                self.assertEqual(parsed.netloc, host)
                self.assertEqual(parsed.path, "/settings/apps/new")

                form_action_csp = self._get_form_action_csp(response)
                self.assertIn("'self'", form_action_csp)
                self.assertIn(f"https://{host}", form_action_csp)
                self.assertContains(
                    response, f'<form method="post" action="{action_url}">'
                )
                content = response.content.decode()
                form_start = content.index(
                    f'<form method="post" action="{action_url}">'
                )
                form_end = content.index("</form>", form_start)
                self.assertNotIn("csrfmiddlewaretoken", content[form_start:form_end])

    def test_register_submit_rejects_invalid_host(self):
        for host in (
            "github.com; script-src *",
            "github.com@attacker.example",
            "github.com:8443",
            "https://github.com",
            "github.com/path",
            "github.com?query=1",
        ):
            with self.subTest(host=host):
                response = self._post_register(host=host)

                self.assertRedirects(response, reverse("github-app-register"))
                self.assertNotIn("github_app_register_nonce", self.client.session)

    def test_register_rejects_prefilled_invalid_host(self):
        response = self.client.get(
            reverse("github-app-register"),
            {"host": "github.com@attacker.example"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["hostname"], "github.com")
        self.assertNotContains(response, "attacker.example")

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
        self.assertNotIn("installation", manifest["default_events"])
        self.assertNotIn("installation_repositories", manifest["default_events"])

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
        submit = self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url(submit)).query)["state"][0]

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
        submit = self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url(submit)).query)["state"][0]
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
        submit = self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url(submit)).query)["state"][0]

        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "x", "state": state},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

    def test_register_requires_management_configure(self):
        user = User.objects.create_user(
            username="manager",
            email="manager@example.org",
            password="testpassword",
        )
        self._grant_global_permissions(user, "management.use")
        self.client.login(username=user.username, password="testpassword")

        protected_urls: tuple[tuple[str, str, dict[str, str]], ...] = (
            ("get", reverse("github-app-register"), {}),
            ("post", reverse("github-app-register-submit"), {}),
            ("get", reverse("github-app-register-callback"), {}),
        )
        for method, url, data in protected_urls:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, data)
                self.assertEqual(response.status_code, 403)

        self._grant_global_permissions(user, "management.configure")

        response = self.client.get(reverse("github-app-register"))
        self.assertEqual(response.status_code, 200)

    def test_remove_app_requires_management_configure(self):
        user = User.objects.create_user(
            username="manager",
            email="manager@example.org",
            password="testpassword",
        )
        self._grant_global_permissions(user, "management.use")
        self.client.login(username=user.username, password="testpassword")
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate",
            private_key="pem",
            webhook_secret="wh",
        )

        response = self.client.post(
            reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(GitHubAppCredentials.objects.filter(pk=credentials.pk).exists())

        self._grant_global_permissions(user, "management.configure")

        response = self.client.post(
            reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(
            GitHubAppCredentials.objects.filter(pk=credentials.pk).exists()
        )

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
        self.assertContains(response, "already has stored GitHub App credentials")
        content = response.content.decode()
        button_start = content.index('type="submit"')
        button_end = content.index("</button>", button_start)
        self.assertNotIn("disabled", content[button_start:button_end])

        response = self._post_register(host="github.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered for github.com")
        self.assertNotIn("github_app_register_nonce", self.client.session)

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
        self.assertTrue(response.context["apps"][0]["can_remove"])

    def test_credentials_page_disables_remove_app_with_connected_accounts(self):
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
        )
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=Workspace.objects.create(name="Connected Workspace"),
        )

        response = self.client.get(reverse("manage-github-accounts"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["apps"][0]["can_remove"])
        self.assertContains(response, "Remove connected GitHub accounts first.")
        self.assertNotContains(
            response,
            f'data-bs-target="#remove-app-{credentials.pk}"',
        )
        self.assertNotContains(
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

    def test_credentials_remove_app_credentials_rejects_connected_accounts(self):
        credentials = GitHubAppCredentials.objects.create(
            hostname="github.com",
            app_id="111",
            app_slug="weblate-on-com",
            private_key="pem",
            webhook_secret="wh",
        )
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=Workspace.objects.create(name="Connected Workspace"),
        )

        response = self.client.post(
            reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertTrue(GitHubAppCredentials.objects.filter(pk=credentials.pk).exists())
