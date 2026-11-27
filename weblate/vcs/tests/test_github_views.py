# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import timedelta
from typing import cast
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.shortcuts import render
from django.template import Context, Template
from django.test import TestCase
from django.test.utils import CaptureQueriesContext, modify_settings, override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.auth.models import Group, Permission, Role, User, UserBlock
from weblate.checks.locks import lock_check_projects
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, Change, Component, Project
from weblate.trans.tests.test_views import ReusableViewTestCase, ViewTestCase
from weblate.utils.change_origin import acting_user_context
from weblate.utils.site import get_site_url
from weblate.utils.tests import http_mock
from weblate.utils.tests.network import mock_dns
from weblate.vcs.github import (
    GITHUB_APP_MANIFEST_EVENTS,
    GITHUB_APP_MANIFEST_PERMISSIONS,
    GitHubAppCredentials,
    GithubAppRepository,
    GitHubInstallation,
)
from weblate.vcs.models import InstallationProvider, PendingInstallation
from weblate.vcs.pending import PENDING_GITHUB_INSTALLATION_RETENTION
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


class GitHubInstallationViewTest(ReusableViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enterContext(
            mock_dns("api.github.com", "github.com", "github.example.com")
        )
        cache.clear()
        self.user.is_superuser = True
        self.user.save()

        self.workspace = Workspace.objects.create(name="Test Workspace")
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])

        self._make_credentials()

    def assert_workspace_breadcrumbs(self, response, *, connections_page=False) -> None:
        document = BeautifulSoup(response.content, "html.parser")
        links = [link["href"] for link in document.select(".breadcrumb a")]
        expected = [self.workspace.get_absolute_url()]
        if not connections_page:
            expected.append(reverse("workspace-integrations", args=[self.workspace.pk]))
        self.assertEqual(links, expected)

    def assert_integration_markup(self, response, headings: list[str]) -> None:
        document = BeautifulSoup(response.content, "html.parser")
        self.assertIsNotNone(document.select_one("h1"))
        self.assertIsNotNone(document.select_one("ol.breadcrumb"))
        self.assertEqual(
            [
                heading.name
                for heading in document.select(".main-content :is(h2, h3, h4, h5)")
            ],
            headings,
        )
        for item in document.select(".breadcrumb-item"):
            parent = item.parent
            self.assertIn(parent.name if parent is not None else None, {"ol", "ul"})
        for element in document.select(".breadcrumb, .main-content .card-body ul"):
            for child in element.find_all(recursive=False):
                self.assertIn(child.name, {"li", "script", "template", "style"})
            self.assertFalse(
                any(
                    text.strip()
                    for text in element.find_all(string=True, recursive=False)
                )
            )

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
        user.clear_permissions_cache()

    def _mock_oauth(
        self,
        *,
        hostname: str = "github.com",
        accessible_ids: tuple[str, ...] = ("12345",),
        managed_installation_ids: tuple[str, ...] | None = None,
        installations: list[dict] | None = None,
        token: str = "ghu_user",  # ruff: ignore[hardcoded-password-default]
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
        http_mock.register(
            "POST",
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
        http_mock.register(
            "GET",
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
            http_mock.register(
                "GET",
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
        http_mock.register(
            "GET",
            "https://api.github.com/app/installations/12345",
            json={"id": 12345, "account": account},
        )
        http_mock.register(
            "POST",
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        http_mock.register(
            "GET",
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

    def _remove_workspaces(self) -> None:
        self.project.workspace = None
        self.project.save(update_fields=["workspace"])
        self.workspace.delete()
        self.user.clear_permissions_cache()

    def assert_missing_workspace_message(self, response) -> None:
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(
            response_messages,
            [
                (
                    "Create a workspace before connecting a GitHub account. "
                    "GitHub App connections are linked to workspaces."
                )
            ],
        )

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
        self.assertContains(response, "Remove connected account?")
        self.assertContains(response, "will also be uninstalled from GitHub")
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

    def test_install_redirects_to_github(self) -> None:
        location = self._start_install(reverse("github-app-repositories"))
        parsed = urlparse(location)

        self.assertEqual(parsed.netloc, "github.com")
        self.assertEqual(parsed.path, "/apps/weblate-app/installations/select_target")
        self.assertIn("state", parse_qs(parsed.query))

    def test_install_without_workspace_redirects_with_message(self) -> None:
        self._remove_workspaces()

        response = self.client.get(reverse("github-app-install"))

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assert_missing_workspace_message(response)

    def test_setup_without_workspace_redirects_with_message(self) -> None:
        self._remove_workspaces()

        response = self.client.get(
            reverse("github-app-setup"),
            {
                "installation_id": "12345",
                "setup_action": "install",
                "code": "oauth-code",
            },
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )
        self.assert_missing_workspace_message(response)

    def test_management_overview_links_to_migration_and_connections(self) -> None:
        response = self.client.get(reverse("manage-github-accounts"))
        migration = reverse("manage-github-migration", args=["github.com"])

        self.assertContains(response, migration)
        self.assertContains(
            response, reverse("manage-github-connections", query={"host": "github.com"})
        )
        response = self.client.get(migration)
        install_url = reverse(
            "github-app-install",
            query={
                "next": migration,
                "host": "github.com",
                "workspace": self.workspace.pk,
            },
        )
        self.assertContains(response, install_url.replace("&", "&amp;"))

    def test_account_vcs_integrations_requires_login(self) -> None:
        self.client.logout()

        response = self.client.get(reverse("account-vcs"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_profile_omits_link_to_legacy_integrations(self) -> None:
        response = self.client.get(reverse("profile"))
        self.assertNotContains(response, reverse("account-vcs"))
        self.assertRedirects(
            self.client.get(
                reverse("account-vcs", query={"workspace": self.workspace.pk})
            ),
            reverse("workspace-integrations", args=[self.workspace.pk]),
        )

    def test_legacy_integrations_redirects_to_workspaces_without_managed_workspaces(
        self,
    ) -> None:
        self.client.force_login(self.anotheruser)
        self.assertRedirects(
            self.client.get(reverse("account-vcs")), reverse("workspaces")
        )

    def test_legacy_integrations_redirects_project_admin_to_workspace(self) -> None:
        self.project.add_user(self.anotheruser, "Administration")
        self.client.force_login(self.anotheruser)

        self.assertRedirects(
            self.client.get(reverse("account-vcs")),
            reverse("workspace-integrations", args=[self.workspace.pk]),
        )

    def test_legacy_integrations_lists_only_managed_workspaces(self) -> None:
        second = Workspace.objects.create(name="Second managed workspace")
        other = Project.objects.create(
            name="Second managed project", slug="second-managed", workspace=second
        )
        hidden = Workspace.objects.create(name="Hidden workspace")
        for project in (self.project, other):
            project.add_user(self.anotheruser, "Administration")
        self.client.force_login(self.anotheruser)
        url = reverse("account-vcs")

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)

        self.assertContains(response, "Choose a workspace for code-hosting connections")
        self.assert_integration_markup(response, ["h2"])
        self.assertCountEqual(
            list(response.context["workspace_page"]), [self.workspace, second]
        )
        self.assertContains(
            response, reverse("workspace-integrations", args=[second.pk])
        )
        self.assertNotContains(
            response, reverse("workspace-integrations", args=[hidden.pk])
        )
        self.assertFalse(
            any(
                '"vcs_installation"' in query["sql"]
                for query in queries.captured_queries
            )
        )
        self.assertEqual(
            list(self.client.get(url, {"q": "Second"}).context["workspace_page"]),
            [second],
        )

    def test_account_vcs_integrations_uses_workspace_scope(self) -> None:
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
        GitHubInstallation.objects.create(
            installation_id="7890",
            target_login="second-workspace-org",
            workspace=other_workspace,
        )
        self.client.login(username=user.username, password="testpassword")

        response = self.client.get(
            reverse("workspace-integrations", args=[self.workspace.pk])
        )

        self.assertContains(response, "test-org")
        self.assertContains(response, self.workspace.name)
        self.assertNotContains(response, "hidden-org")
        self.assertNotContains(response, "second-workspace-org")
        self.assertContains(
            response,
            reverse("manage-github-account-refresh", kwargs={"pk": installation.pk}),
        )
        self.assertContains(
            response,
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )
        self.assert_installation_remove_modal(response, installation)
        install_url = reverse(
            "github-app-install",
            query={
                "next": reverse("workspace-integrations", args=[self.workspace.pk]),
                "host": "github.com",
                "workspace": self.workspace.pk,
            },
        )
        self.assertContains(response, install_url.replace("&", "&amp;"))
        self.assertEqual(
            self.client.get(
                reverse("account-vcs", query={"workspace": hidden_workspace.pk})
            ).status_code,
            403,
        )

    def test_project_admin_cannot_manage_account_vcs_integrations(self) -> None:
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

        response = self.client.get(
            reverse("workspace-integrations", args=[self.workspace.pk])
        )

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

    def test_project_admin_cannot_manage_github_installation(self) -> None:
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

    def test_account_vcs_integrations_filters_selected_workspace(self) -> None:
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
            reverse("workspace-integrations", args=[self.workspace.pk])
        )

        self.assert_workspace_breadcrumbs(response, connections_page=True)
        self.assertEqual(response.context["selected_workspace"], self.workspace)
        self.assertContains(response, "test-org")
        self.assertContains(response, self.workspace.name)
        self.assertNotContains(response, "other-org")
        self.assertNotContains(response, other_workspace.name)
        next_url = reverse("workspace-integrations", args=[self.workspace.pk])
        install_url = (
            f"{reverse('github-app-install')}?"
            f"{urlencode({'next': next_url, 'host': 'github.com', 'workspace': self.workspace.pk})}"
        )
        self.assertNotContains(response, install_url.replace("&", "&amp;"))

    def test_account_vcs_integrations_accepts_workspace_owner(self) -> None:
        owner = User.objects.create_user(
            username="workspace owner",
            email="workspaceowner@example.org",
            password="testpassword",
        )
        self.workspace.add_owner(owner)
        self.client.login(username=owner.username, password="testpassword")

        response = self.client.get(
            reverse("workspace-integrations", args=[self.workspace.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_workspace"], self.workspace)
        self.assertContains(response, "Connect GitHub account")

    def test_account_vcs_integrations_shows_unregistered_apps(self) -> None:
        GitHubInstallation.objects.create(
            hostname="github.example.com",
            installation_id="12345",
            target_type="Organization",
            target_login="stale-org",
            workspace=self.workspace,
            repositories=[_repo_entry("stale-org/repo1")],
        )

        response = self.client.get(
            reverse("workspace-integrations", args=[self.workspace.pk])
        )

        self.assertContains(response, "github.example.com")
        self.assertContains(response, "stale-org")
        self.assertContains(response, "Not registered")

    def test_install_requires_host_selection_with_multiple_configs(self) -> None:
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
        self.assert_workspace_breadcrumbs(response)
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

    @http_mock.activate
    def test_setup_connects_installation(self) -> None:
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
            [(call.request.method, call.request.url) for call in http_mock.calls],
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

    def test_site_manager_existing_installation_groups(self) -> None:
        owned = Workspace.objects.create(name="Owned workspace")
        other = Workspace.objects.create(name="Other workspace")
        for workspace, login, installation_id in (
            (other, "Alpha", "1"),
            (other, "zulu", "2"),
            (owned, "zulu", "2"),
            (owned, "Bravo", "3"),
            (owned, "already-connected", "4"),
            (self.workspace, "already-connected", "4"),
        ):
            GitHubInstallation.objects.create(
                workspace=workspace, target_login=login, installation_id=installation_id
            )

        url = reverse("github-app-install")
        query = {"workspace": str(self.workspace.pk)}
        with patch("weblate.vcs.views.LIST_PAGE_SIZE", 2):
            for page in (1, 2):
                with self.subTest(page=page):
                    response = self.client.get(url, {**query, "page": page})
                    document = BeautifulSoup(response.content, "html.parser")
                    self.assertEqual(
                        [
                            label.get_text(strip=True)
                            for label in document.select("details summary")
                        ],
                        ["Other accounts"],
                    )
        self.assertEqual(response.context["choices"], [])

        owned.add_owner(self.user)
        response = self.client.get(url, query)
        self.assertEqual(
            [login for login, _ in response.context["choices"]], ["Bravo", "zulu"]
        )
        document = BeautifulSoup(response.content, "html.parser")
        self.assertEqual(
            [
                a.get_text(strip=True)
                for a in document.select("details:not([open]) li a")
            ],
            ["Alpha"],
        )
        self.assertNotContains(response, "already-connected")

    @http_mock.activate
    def test_reuse_personal_installation_in_another_workspace(self) -> None:
        repositories = [_repo_entry("octocat/repo1", default_branch="stable")]
        original = Workspace.objects.create(name="Original workspace")
        owner = self.anotheruser
        original.add_owner(owner)
        self.workspace.add_owner(owner)
        self.client.force_login(owner)
        source = GitHubInstallation.objects.create(
            workspace=original,
            installation_id="12345",
            target_type="User",
            target_login="octocat",
        )
        GitHubInstallation.objects.create(
            workspace=Workspace.objects.create(name="Unrelated workspace"),
            installation_id="54321",
            target_type="User",
            target_login="other-owner",
        )
        next_url = reverse("workspace-integrations", args=[self.workspace.pk])
        response = self.client.get(
            reverse("github-app-install"),
            {"workspace": str(self.workspace.pk), "next": next_url},
        )
        self.assert_workspace_breadcrumbs(response)
        self.assertNotContains(response, "other-owner")
        self.assertNotContains(response, "Other accounts")
        [(login, authorize_url)] = response.context["choices"]
        self.assertContains(response, login)
        self.assertEqual(login, "octocat")
        url = urlparse(authorize_url)
        self.assertEqual(url.netloc, "github.com")
        self.assertEqual(url.path, "/login/oauth/authorize")
        state = parse_qs(url.query)["state"][0]

        self._mock_oauth(
            installations=[
                {"id": 12345, "account": {"login": "octocat", "type": "User"}}
            ]
        )
        http_mock.register(
            "GET",
            "https://api.github.com/user",
            json={"login": "octocat"},
        )
        self._mock_setup_api(
            repositories=repositories,
            account={"login": "octocat", "type": "User"},
        )
        response = self.client.get(
            reverse("github-app-setup"),
            {"state": state, "code": "oauth-code"},
        )

        self.assertRedirects(response, next_url)
        source.refresh_from_db()
        self.assertEqual(source.workspace_id, original.pk)
        connected = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertEqual(connected.target_login, "octocat")
        self.assertEqual(connected.target_type, "User")
        self.assertEqual(connected.repositories, repositories)
        self.assertEqual(
            [(call.request.method, call.request.url) for call in http_mock.calls],
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

    @http_mock.activate
    def test_setup_persists_pending_installation_when_api_not_ready(self) -> None:
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
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("connection is pending", response_messages[0])
        self.assertIn("Try connecting the account again later", response_messages[0])

    @override_settings(RATELIMIT_GITHUB_SETUP_ATTEMPTS=0)
    def test_setup_rate_limited(self) -> None:
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self.workspace.add_owner(self.user)
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )

        self.assertRedirects(response, next_url)
        self.assertFalse(
            GitHubInstallation.objects.filter(installation_id="12345").exists()
        )
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn(
            "Too many GitHub account connection attempts", response_messages[0]
        )
        self.assertIn("might still be pending", response_messages[0])
        self.assertIn("Try connecting the account again later", response_messages[0])

    @http_mock.activate
    def test_setup_applies_pending_installation_webhook(self) -> None:
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
            },
        )
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
        self.assertFalse(
            PendingInstallation.objects.filter(
                provider=InstallationProvider.GITHUB,
                hostname="github.com",
                installation_id="12345",
            ).exists()
        )

    @http_mock.activate
    def test_setup_ignores_stale_pending_installation_webhook(self) -> None:
        pending = PendingInstallation.objects.create(
            provider=InstallationProvider.GITHUB,
            hostname="github.com",
            installation_id="12345",
            payload={
                "action": "created",
                "installation": {
                    "id": 12345,
                    "app_id": 99999,
                    "account": {"login": "stale-org", "type": "Organization"},
                },
            },
        )
        PendingInstallation.objects.filter(pk=pending.pk).update(
            updated=timezone.now()
            - PENDING_GITHUB_INSTALLATION_RETENTION
            - timedelta(seconds=1)
        )
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
        self.assertEqual(connected.repositories, repositories)
        # Expired pending rows are ignored here and left for the periodic cleanup task.
        self.assertTrue(PendingInstallation.objects.filter(pk=pending.pk).exists())

    def test_setup_rejects_missing_oauth_code(self) -> None:
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

    def test_setup_update_accepts_existing_installation_without_state(self) -> None:
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self.project.add_user(self.user, "Administration")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "setup_action": "update"},
        )

        self.assertRedirects(
            response,
            f"{reverse('github-app-repositories')}?workspace={self.workspace.pk}",
        )
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(response_messages, ["Connected GitHub account updated."])

    @http_mock.activate
    def test_setup_update_recovers_unlinked_installation(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(
            vcs="git", repo="git@github.com:test-org/repo1.git"
        )
        url = f"{reverse('github-app-setup')}?setup_action=update&installation_id=12345"
        response = self.client.get(url)
        self.assertContains(response, "Authorize on GitHub")
        response = self.client.post(
            url, {"workspace": self.workspace.pk, "host": "github.com"}
        )
        authorize = urlparse(response["Location"])
        self.assertEqual(
            (authorize.netloc, authorize.path), ("github.com", "/login/oauth/authorize")
        )
        self.assertFalse(GitHubInstallation.objects.exists())
        self._mock_oauth()
        repositories = self._mock_setup_api()
        response = self.client.get(
            reverse("github-app-setup"),
            {
                "state": parse_qs(authorize.query)["state"][0],
                "code": "fresh-code",
            },
        )
        self.assertRedirects(
            response,
            f"{reverse('github-app-repositories')}?workspace={self.workspace.pk}",
        )
        connected = GitHubInstallation.objects.get(
            workspace=self.workspace, installation_id="12345"
        )
        self.assertEqual(connected.repositories, repositories)
        migration = self.client.get(
            reverse("github-app-migration", kwargs={"workspace_id": self.workspace.pk})
        )
        self.assertIn(
            self.component,
            [entry["component"] for entry in migration.context["available_entries"]],
        )

    @http_mock.activate
    def test_setup_recovery_limits_workspace_and_host_choices(self) -> None:
        self.client.force_login(self.anotheruser)
        self.workspace.add_owner(self.anotheruser)
        other = Workspace.objects.create(name="Inaccessible workspace")
        self._make_credentials("github.example.com", client_id="enterprise-client")
        url = f"{reverse('github-app-setup')}?setup_action=update&installation_id=12345"
        response = self.client.get(url)
        self.assertNotContains(response, other.name)
        for workspace, host, field in (
            (other.pk, "github.example.com", "workspace"),
            (self.workspace.pk, "unknown.example.com", "host"),
        ):
            response = self.client.post(url, {"workspace": workspace, "host": host})
            self.assertIn(field, response.context["form"].errors)
        response = self.client.post(
            url, {"workspace": self.workspace.pk, "host": "github.example.com"}
        )
        authorize = urlparse(response["Location"])
        self.assertEqual(authorize.netloc, "github.example.com")
        params = parse_qs(authorize.query)
        self.assertEqual(params["client_id"], ["enterprise-client"])
        self.assertEqual(
            params["redirect_uri"], [get_site_url(reverse("github-app-setup"))]
        )
        self._mock_oauth(hostname="github.example.com", managed_installation_ids=())
        response = self.client.get(
            reverse("github-app-setup"),
            {"state": params["state"][0], "code": "oauth-code"},
        )
        self.assertRedirects(
            response,
            f"{reverse('github-app-repositories')}?workspace={self.workspace.pk}",
        )
        self.assertFalse(GitHubInstallation.objects.exists())

    @http_mock.activate
    def test_setup_recovery_rechecks_workspace_permission(self) -> None:
        owner = self.anotheruser
        self.workspace.add_owner(owner)
        self.client.force_login(owner)
        url = f"{reverse('github-app-setup')}?setup_action=update&installation_id=12345"
        response = self.client.post(
            url, {"workspace": self.workspace.pk, "host": "github.com"}
        )
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        owner.remove_team(None, self.workspace.get_owners_group())
        response = self.client.get(
            reverse("github-app-setup"), {"state": state, "code": "oauth-code"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(http_mock.calls)
        self.assertFalse(GitHubInstallation.objects.exists())

    def test_setup_update_rejects_tampered_state(self) -> None:
        response = self.client.get(
            reverse("github-app-setup"),
            {
                "setup_action": "update",
                "state": "tampered",
                "installation_id": "12345",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "installation link is no longer valid",
            str(next(iter(get_messages(response.wsgi_request)))),
        )

    def test_setup_update_rejects_inaccessible_installation_without_state(self) -> None:
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self.project.add_user(self.user, "Administration")
        other_workspace = Workspace.objects.create(name="Other GitHub Workspace")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=other_workspace,
        )

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "setup_action": "update"},
        )

        self.assertRedirects(response, reverse("github-app-repositories"))
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("installation link is no longer valid", response_messages[0])

    def test_setup_update_accepts_installation_for_management_user(self) -> None:
        # Site-wide managers (management.use) may handle update callbacks for
        # installations in any workspace, not just ones they manage directly.
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self._grant_management_permission(self.user)
        other_workspace = Workspace.objects.create(name="Other GitHub Workspace")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=other_workspace,
        )

        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "setup_action": "update"},
        )

        self.assertRedirects(
            response,
            reverse("manage-github-account-detail", kwargs={"pk": installation.pk}),
        )
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(response_messages, ["Connected GitHub account updated."])

    @http_mock.activate
    def test_setup_update_with_state_runs_full_setup(self) -> None:
        # An update callback that carries a signed Weblate state is a
        # Weblate-initiated install flow and must run the full setup (OAuth
        # verification + repository refresh), not the stateless shortcut.
        repositories = [_repo_entry("test-org/repo1")]
        next_url = "/create/component/#github"
        install_url = self._start_install(next_url)
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(accessible_ids=("12345",))
        self._mock_setup_api(repositories=repositories)
        response = self.client.get(
            reverse("github-app-setup"),
            {
                "installation_id": "12345",
                "state": state,
                "code": "oauth-code",
                "setup_action": "update",
            },
        )

        self.assertRedirects(response, next_url)
        connected = GitHubInstallation.objects.get(
            installation_id="12345", workspace=self.workspace
        )
        self.assertEqual(connected.repositories, repositories)
        self.assertIsNotNone(connected.repositories_updated)

    @http_mock.activate
    def test_setup_rejects_malformed_installation_id(self) -> None:
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        response = self.client.get(
            reverse("github-app-setup"),
            {
                "installation_id": "12345/access_tokens",
                "state": state,
                "code": "oauth-code",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(GitHubInstallation.objects.exists())
        self.assertEqual(len(http_mock.calls), 0)
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(
            response_messages, ["GitHub did not return a valid installation ID."]
        )

    @http_mock.activate
    def test_setup_rejects_foreign_installation_id(self) -> None:
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
            [(call.request.method, call.request.url) for call in http_mock.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
            ],
        )

    @http_mock.activate
    def test_setup_rejects_personal_installation_for_non_owner(self) -> None:
        install_url = self._start_install("/create/component/#github")
        state = parse_qs(urlparse(install_url).query)["state"][0]

        self._mock_oauth(
            installations=[
                {"id": 12345, "account": {"login": "octocat", "type": "User"}}
            ]
        )
        http_mock.register(
            "GET",
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
            [(call.request.method, call.request.url) for call in http_mock.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
                ("GET", "https://api.github.com/user"),
            ],
        )

    @http_mock.activate
    def test_setup_rejects_org_installation_without_admin_access(self) -> None:
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
            [(call.request.method, call.request.url) for call in http_mock.calls],
            [
                ("POST", "https://github.com/login/oauth/access_token"),
                ("GET", "https://api.github.com/user/installations?per_page=100"),
                (
                    "GET",
                    "https://api.github.com/orgs/test-org/installations?per_page=100",
                ),
            ],
        )

    @http_mock.activate
    def test_setup_reauthorizes_after_rejected_code(self) -> None:
        next_url = "/create/component/#github"
        state = parse_qs(urlparse(self._start_install(next_url)).query)["state"][0]
        params = {"installation_id": "12345", "state": state, "code": "stale-code"}
        http_mock.register(
            "POST",
            "https://github.com/login/oauth/access_token",
            json={"error": "bad_verification_code"},
        )
        for _ in range(2):
            response = self.client.get(reverse("github-app-setup"), params)
            self.assertContains(response, "Authorize again")
            self.assertFalse(GitHubInstallation.objects.exists())
            url = urlparse(response.context["authorize_url"])
            self.assertEqual(
                (url.netloc, url.path), ("github.com", "/login/oauth/authorize")
            )
            params = {"state": parse_qs(url.query)["state"][0], "code": "another-code"}

        http_mock.unregister("POST", "https://github.com/login/oauth/access_token")
        self._mock_oauth()
        self._mock_setup_api()
        response = self.client.get(reverse("github-app-setup"), params)
        self.assertRedirects(response, next_url)
        self.assertTrue(
            GitHubInstallation.objects.filter(
                workspace=self.workspace, installation_id="12345"
            ).exists()
        )

    def test_repository_list_uses_workspace_scope(self) -> None:
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
        self.enterContext(acting_user_context(self.user))
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

        self.workspace.add_owner(self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse("github-app-repositories"))

        self.assertContains(response, "Find a workspace")
        self.assertNotContains(response, "test-org/repo1")
        self.assertNotContains(response, "other-org/repo2")
        self.assertEqual(
            list(response.context["workspace_page"]), [self.workspace, other_workspace]
        )

        self.client.force_login(user)
        response = self.client.get(reverse("github-app-repositories"))
        self.assert_workspace_breadcrumbs(response)
        self.assertContains(response, "test-org/repo1")
        self.assertNotContains(response, "other-org/repo2")
        self.assertEqual(
            self.client.get(
                reverse(
                    "github-app-repositories", query={"workspace": other_workspace.pk}
                )
            ).status_code,
            403,
        )

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_creation_picker_uses_workspaces_with_eligible_projects(self) -> None:
        other = Workspace.objects.create(name="Connection-only workspace")
        self.project.add_user(self.anotheruser, "Administration")
        other.add_owner(self.anotheruser)
        repo = _repo_entry("test-org/eligible")
        installation = GitHubInstallation.objects.create(
            workspace=self.workspace,
            installation_id="12345",
            target_login="test-org",
            repositories=[repo],
        )
        other_repo = _repo_entry("other-org/no-destination")
        other_installation = GitHubInstallation.objects.create(
            workspace=other,
            installation_id="23456",
            target_login="other-org",
            repositories=[other_repo],
        )
        self.client.force_login(self.anotheruser)
        picker_url = reverse("github-app-creation-repositories")
        response = self.client.get(picker_url)
        import_url = reverse(
            "github-app-creation-repository-import",
            args=[installation.pk, repo["full_name"]],
        )

        self.assertEqual(response.context["selected_workspace"], self.workspace)
        self.assertContains(response, import_url)
        self.assertNotContains(response, other_repo["full_name"])
        self.assertRedirects(
            self.client.get(import_url),
            reverse("create-component-vcs", query={"session_component": 1}),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.get(picker_url, {"workspace": str(other.pk)}).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "github-app-creation-repository-import",
                    args=[other_installation.pk, other_repo["full_name"]],
                )
            ).status_code,
            403,
        )
        self.assertContains(
            self.client.get(
                reverse("github-app-repositories"), {"workspace": str(other.pk)}
            ),
            other_repo["full_name"],
        )

    def test_repository_list_for_project_without_workspace(self) -> None:
        user = self.anotheruser
        self.workspace.add_owner(user)
        self.project.add_user(user, "Administration")
        Project.objects.filter(pk=self.project.pk).update(workspace=None)
        GitHubInstallation.objects.create(
            workspace=self.workspace,
            installation_id="12345",
            target_login="test-org",
            repositories=[_repo_entry("test-org/repo1")],
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("github-app-repositories"), {"project": self.project.pk}
        )

        self.assertContains(response, "Select a project with a workspace")
        self.assertNotContains(response, reverse("github-app-install"))
        self.assertNotContains(response, "test-org/repo1")
        document = BeautifulSoup(response.content, "html.parser")
        self.assertEqual(
            [link["href"] for link in document.select(".breadcrumb a")],
            [reverse("create-component")],
        )

    def test_repository_list_hides_hosts_without_credentials(self) -> None:
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

    def test_installation_detail_warns_about_affected_components(self) -> None:
        repo = _repo_entry("test-org/repo1")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )
        Component.objects.filter(pk=self.component.pk).update(
            vcs="github-app", repo="https://github.com/test-org/repo1.git"
        )

        response = self.client.get(
            reverse("manage-github-account-detail", kwargs={"pk": installation.pk})
        )

        self.assertContains(response, "will lose access to its repository")
        self.assertContains(response, str(self.component))

    def test_account_list_prefetches_affected_components(self) -> None:
        """Rendering many removal modals must not query components per row."""
        repo = _repo_entry("test-org/repo1")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )
        for index in range(3):
            GitHubInstallation.objects.create(
                installation_id=f"5432{index}",
                target_type="Organization",
                target_login=f"other-org-{index}",
                workspace=self.workspace,
                repositories=[repo],
            )
        Component.objects.filter(pk=self.component.pk).update(
            vcs="github-app", repo="https://github.com/test-org/repo1.git"
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("workspace-integrations", args=[self.workspace.pk])
            )

        self.assertContains(response, "will lose access to its repository")
        self.assertContains(response, str(self.component))
        self.assertEqual(
            len(
                [
                    query
                    for query in queries.captured_queries
                    if '"trans_component"."vcs" = ' in query["sql"]
                    or '"trans_component"."vcs" IN ' in query["sql"]
                ]
            ),
            2,
        )

    def test_installation_detail_hides_import_link_when_disabled(self) -> None:
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

    def test_installation_detail_hides_import_link_without_credentials(self) -> None:
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

    def test_site_manager_can_import_from_installation_detail(self) -> None:
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

        self.assert_workspace_breadcrumbs(response)
        connections = self.client.get(
            reverse("workspace-integrations", args=[self.workspace.pk])
        )
        self.assert_workspace_breadcrumbs(connections, connections_page=True)
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

        self.project.add_user(manager, "Administration")
        category = Category.objects.create(
            project=self.project, name="Import target", slug="import-target"
        )
        for scope in ({"project": self.project.pk}, {"category": category.pk}):
            with self.subTest(scope=scope):
                self.assertRedirects(
                    self.client.get(_import_url(installation, repo, **scope)),
                    reverse("create-component-vcs", query={"session_component": 1}),
                    fetch_redirect_response=False,
                )
                params = self.client.session["session_component"]
                self.assertEqual(params["project"], self.project.pk)
                self.assertEqual(params.get("category"), scope.get("category"))

    def test_repository_import_link_preselects_github_app_vcs(self) -> None:
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

    def test_repository_import_uses_create_session(self) -> None:
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

    def test_repository_list_omits_archived_repositories(self) -> None:
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

    @http_mock.activate
    def test_refresh_repositories_updates_installation(self) -> None:
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        repo = _repo_entry("test-org/repo1", default_branch="stable")

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
                    repo,
                    _repo_entry("test-org/archived", archived=True),
                ]
            },
        )
        self.async_client.force_login(self.user)
        response = async_to_sync(self.async_client.post)(
            reverse("manage-github-account-refresh", kwargs={"pk": installation.pk}),
            {"next": reverse("github-app-repositories")},
        )

        self.assertRedirects(
            response,
            reverse("github-app-repositories"),
            fetch_redirect_response=False,
        )
        installation.refresh_from_db()
        self.assertEqual(installation.repositories, [repo])
        self.assertIsNotNone(installation.repositories_updated)
        self.assertEqual(
            [(call.request.method, call.request.url) for call in http_mock.calls],
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

    def test_refresh_repositories_rejects_get(self) -> None:
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

    @http_mock.activate
    def test_remove_installation(self) -> None:
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        http_mock.register(
            "DELETE",
            "https://api.github.com/app/installations/12345",
            status_code=202,
        )

        self.async_client.force_login(self.user)
        response = async_to_sync(self.async_client.post)(
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )

        self.assertRedirects(
            response,
            reverse("manage-github-connections", query={"host": installation.hostname}),
            fetch_redirect_response=False,
        )
        self.assertFalse(GitHubInstallation.objects.filter(pk=installation.pk).exists())
        self.assertEqual(
            [(call.request.method, call.request.url) for call in http_mock.calls],
            [("DELETE", "https://api.github.com/app/installations/12345")],
        )
        response_messages = [
            str(message) for message in get_messages(response.asgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("uninstalled the Weblate GitHub App", response_messages[0])

    @http_mock.activate
    def test_remove_installation_accepts_missing_github_installation(self) -> None:
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        http_mock.register(
            "DELETE",
            "https://api.github.com/app/installations/12345",
            status_code=404,
        )

        self.async_client.force_login(self.user)
        response = async_to_sync(self.async_client.post)(
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )

        self.assertRedirects(
            response,
            reverse("manage-github-connections", query={"host": installation.hostname}),
            fetch_redirect_response=False,
        )
        self.assertFalse(GitHubInstallation.objects.filter(pk=installation.pk).exists())

    @http_mock.activate
    def test_remove_installation_keeps_row_when_github_uninstall_fails(self) -> None:
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        http_mock.register(
            "DELETE",
            "https://api.github.com/app/installations/12345",
            status_code=500,
        )

        self.async_client.force_login(self.user)
        with patch("weblate.vcs.github.report_error") as report_error:
            response = async_to_sync(self.async_client.post)(
                reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
            )

        self.assertRedirects(
            response,
            reverse("manage-github-connections", query={"host": installation.hostname}),
            fetch_redirect_response=False,
        )
        self.assertTrue(GitHubInstallation.objects.filter(pk=installation.pk).exists())
        report_error.assert_called_once()
        self.assertEqual(
            report_error.call_args.args,
            ("Failed to uninstall connected GitHub account",),
        )
        self.assertIsInstance(report_error.call_args.kwargs["exception"], BaseException)
        response_messages = [
            str(message) for message in get_messages(response.asgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("connection was not removed", response_messages[0])

    @http_mock.activate
    def test_remove_installation_accepts_unauthorized_github_app(self) -> None:
        """A deleted or suspended app must not block removing the connection."""
        for status_code in (401, 403, 410):
            with self.subTest(status_code=status_code):
                installation = GitHubInstallation.objects.create(
                    installation_id="12345",
                    target_type="Organization",
                    target_login="test-org",
                    workspace=self.workspace,
                )
                http_mock.reset()
                http_mock.register(
                    "DELETE",
                    "https://api.github.com/app/installations/12345",
                    status_code=status_code,
                )

                self.async_client.force_login(self.user)
                response = async_to_sync(self.async_client.post)(
                    reverse(
                        "manage-github-account-remove", kwargs={"pk": installation.pk}
                    ),
                )

                self.assertRedirects(
                    response,
                    reverse(
                        "manage-github-connections",
                        query={"host": installation.hostname},
                    ),
                    fetch_redirect_response=False,
                )
                self.assertFalse(
                    GitHubInstallation.objects.filter(pk=installation.pk).exists()
                )
                response_messages = [
                    str(message) for message in get_messages(response.asgi_request)
                ]
                self.assertIn(
                    "no longer grants access to this installation",
                    response_messages[-1],
                )

    @http_mock.activate
    def test_remove_installation_without_app_credentials(self) -> None:
        """Removal must work even once the app credentials are gone."""
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        GitHubAppCredentials.objects.all().delete()

        self.async_client.force_login(self.user)
        response = async_to_sync(self.async_client.post)(
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )

        self.assertRedirects(
            response,
            reverse("manage-github-connections", query={"host": installation.hostname}),
            fetch_redirect_response=False,
        )
        self.assertFalse(GitHubInstallation.objects.filter(pk=installation.pk).exists())
        self.assertEqual(len(http_mock.calls), 0)
        response_messages = [
            str(message) for message in get_messages(response.asgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn(
            "no longer configured on this Weblate instance", response_messages[0]
        )

    @http_mock.activate
    def test_remove_installation_keeps_shared_github_installation(self) -> None:
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
        )
        other_installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=Workspace.objects.create(name="Other GitHub Workspace"),
        )

        self.async_client.force_login(self.user)
        response = async_to_sync(self.async_client.post)(
            reverse("manage-github-account-remove", kwargs={"pk": installation.pk}),
        )

        self.assertRedirects(
            response,
            reverse("manage-github-connections", query={"host": installation.hostname}),
            fetch_redirect_response=False,
        )
        self.assertFalse(GitHubInstallation.objects.filter(pk=installation.pk).exists())
        self.assertTrue(
            GitHubInstallation.objects.filter(pk=other_installation.pk).exists()
        )
        self.assertEqual(len(http_mock.calls), 0)
        response_messages = [
            str(message) for message in get_messages(response.asgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("another workspace still uses it", response_messages[0])

    def test_remove_installation_rejects_get(self) -> None:
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

    def test_migration_lists_components_and_install_url(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(
            vcs="git",
            repo="git@github.com:test-org/repo1.git",
        )
        self.component.refresh_from_db()
        url = reverse(
            "github-app-migration", kwargs={"workspace_id": self.workspace.pk}
        )

        response = self.client.get(url)

        self.assertContains(response, "test-org/repo1")
        self.assertContains(response, "Repository access needed")
        install_url = response.context["github_app_install_url"]
        self.assertTrue(install_url.startswith(reverse("github-app-install")))
        install_query = parse_qs(urlparse(install_url).query)
        self.assertEqual(install_query["workspace"], [str(self.workspace.pk)])
        self.assertEqual(install_query["next"], [url])

    def test_migration_table_mixes_component_states(self) -> None:
        blocked = self.create_po(project=self.project, name="Blocked")
        configured = self.create_po(project=self.project, name="Configured")
        Component.objects.filter(pk=blocked.pk).update(
            repo="https://github.com/missing/repo.git"
        )
        Component.objects.filter(pk=configured.pk).update(
            vcs="github-app", repo="https://github.com/configured/repo.git"
        )
        Component.objects.filter(pk=self.component.pk).update(
            repo="https://github.com/ready/repo.git"
        )
        GitHubInstallation.objects.create(
            workspace=self.workspace,
            installation_id="12345",
            target_login="ready",
            repositories=[_repo_entry("ready/repo")],
        )
        response = self.client.get(
            reverse("github-app-migration", args=[self.workspace.pk])
        )
        document = BeautifulSoup(response.content, "html.parser")
        rows = document.select("form table tbody tr")
        self.assertEqual(len(rows), 3)
        for component, status in (
            (self.component, "Ready"),
            (blocked, "Repository access needed"),
            (configured, "Using GitHub App"),
        ):
            [row] = [
                row for row in rows if row.find("a", href=component.get_absolute_url())
            ]
            self.assertIn(status, row.get_text())
            self.assertEqual(
                bool(row.select('input[name="components"]')),
                component == self.component,
            )
        self.assertEqual(response.context["required_accounts"], ["missing"])

    def test_migration_category_paths(self) -> None:
        parent = None
        categories = []
        for index in range(3):
            parent = Category.objects.create(
                name=f"Migration category {index}",
                slug=f"migration-{index}",
                project=self.project,
                category=parent,
            )
            categories.append(parent)
        Component.objects.filter(pk=self.component.pk).update(
            vcs="git",
            repo="git@github.com:test-org/repo1.git",
            category=parent,
        )
        response = self.client.get(
            reverse("github-app-migration", kwargs={"workspace_id": self.workspace.pk})
        )
        for category in categories:
            self.assertContains(response, f'href="{category.get_absolute_url()}"')
        component = next(
            entry["component"]
            for entry in response.context["entries"]
            if entry["component"].pk == self.component.pk
        )
        template = Template(
            "{% load translations %}{% path_object_links component flags=False %}"
        )
        with self.assertNumQueries(0):
            template.render(Context({"component": component}))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_migration_updates_selected_component(self) -> None:
        repository = _repo_entry("test-org/repo1")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repository],
        )
        Component.objects.filter(pk=self.component.pk).update(
            vcs="git",
            repo="git@github.com:test-org/repo1.git",
            push="git@github.com:weblate/repo1.git",
            push_branch="translations",
            vcs_params={
                "git_force_push": True,
            },
        )
        self.component.refresh_from_db()
        for alert_name in ("GitHubAppMigration", "PushFailure", "UpdateFailure"):
            self.component.add_alert(alert_name)
        url = reverse(
            "github-app-migration", kwargs={"workspace_id": self.workspace.pk}
        )

        response = self.client.post(url)
        self.assertContains(response, "Select at least one component to migrate.")
        self.assert_workspace_breadcrumbs(response)
        document = BeautifulSoup(response.content, "html.parser")
        [checkbox] = document.select('table input[name="components"]')
        self.assertFalse(checkbox.has_attr("checked"))
        self.assertEqual(checkbox["value"], str(self.component.pk))
        [label] = document.find_all("label", attrs={"for": checkbox["id"]})
        self.assertIn(self.component.full_slug, label.get_text())
        response = self.client.post(
            url, {"components": [str(self.component.pk)]}, follow=True
        )
        self.assertRedirects(response, url)
        for page in (response, self.client.get(url)):
            self.assertContains(page, "Using GitHub App")
            self.assertContains(page, f'href="{self.component.get_absolute_url()}"')
            self.assertNotContains(page, "Migrate selected components")
            self.assertNotContains(page, "The GitHub App needs repository access")
        repeated = self.client.post(url, {"components": [str(self.component.pk)]})
        self.assertContains(repeated, "Select a valid choice")
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "github-app")
        self.assertEqual(self.component.repo, repository["clone_url"])
        self.assertEqual(self.component.push, "")
        self.assertEqual(self.component.push_branch, "")
        self.assertEqual(
            self.component.vcs_params,
            {"create_merge_request": False},
        )
        self.assertFalse(
            self.component.alert_set.filter(
                name__in=("GitHubAppMigration", "PushFailure", "UpdateFailure")
            ).exists()
        )

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=False,
        GITHUB_CREDENTIALS={"api.github.com": {"username": "test", "token": "token"}},
    )
    def test_migration_preserves_github_create_merge_request(self) -> None:
        repository = _repo_entry("test-org/repo1")
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repository],
        )
        url = reverse(
            "github-app-migration", kwargs={"workspace_id": self.workspace.pk}
        )

        for create_merge_request in (False, True):
            with self.subTest(create_merge_request=create_merge_request):
                Component.objects.filter(pk=self.component.pk).update(
                    vcs="github",
                    repo="https://github.com/test-org/repo1.git",
                    vcs_params={"create_merge_request": create_merge_request},
                )

                response = self.client.post(
                    url, {"components": [str(self.component.pk)]}
                )

                self.assertRedirects(response, url, fetch_redirect_response=False)
                self.component.refresh_from_db()
                self.assertEqual(self.component.vcs, "github-app")
                self.assertEqual(
                    self.component.vcs_params,
                    {"create_merge_request": create_merge_request},
                )

    def test_migration_rejects_unavailable_component(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(
            vcs="github",
            repo="https://github.com/test-org/repo1.git",
        )
        url = reverse(
            "github-app-migration", kwargs={"workspace_id": self.workspace.pk}
        )

        response = self.client.post(url, {"components": [str(self.component.pk)]})

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Select a valid choice",
            response.context["form"].errors["components"][0],
        )
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "github")

    def test_migration_ignores_archived_repositories(self) -> None:
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1", archived=True)],
        )
        Component.objects.filter(pk=self.component.pk).update(
            vcs="git",
            repo="git@github.com:test-org/repo1.git",
        )
        url = reverse(
            "github-app-migration", kwargs={"workspace_id": self.workspace.pk}
        )

        response = self.client.get(url)

        self.assertEqual(response.context["available_entries"], [])
        self.assertEqual(len(response.context["unavailable_entries"]), 1)
        self.assertContains(response, "Repository access needed")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_site_migration_moves_projects_and_assigns_separate_owners(self) -> None:
        self.project.add_user(self.anotheruser, "Administration")
        Project.objects.filter(pk=self.project.pk).update(workspace=None)
        url = reverse("manage-github-migration", args=["github.com"])
        query = {
            "q": self.project.name,
            "projects_page": "1",
            "unconnected_page": "2",
            "connected_page": "3",
        }
        return_url = reverse(
            "manage-github-migration", args=["github.com"], query=query
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                f"{url}?{urlencode({**query, 'next': 'https://outside.example/'})}",
                {"projects": [self.project.pk], "destination": "separate"},
                follow=True,
            )

        project_locks = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "trans_project"' in query["sql"]
            and (" FOR UPDATE" in query["sql"] or " FOR NO KEY UPDATE" in query["sql"])
        ]
        self.assertTrue(project_locks)
        for sql in project_locks:
            self.assertIn(" FOR NO KEY UPDATE", sql)
        self.assertEqual(response.redirect_chain, [(return_url, 302)])
        self.assert_integration_markup(response, ["h2", "h3", "h3", "h3"])

        destination = Workspace.objects.get(projects=self.project)
        self.assertEqual(destination.name, self.project.name)
        self.assertContains(
            response, reverse("workspace-integrations", args=[destination.pk])
        )
        owners = destination.get_owners_group()
        self.assertTrue(owners.user_set.filter(pk=self.anotheruser.pk).exists())
        self.assertTrue(owners.user_set.filter(pk=self.user.pk).exists())
        self.assertTrue(
            Change.objects.filter(
                action=ActionEvents.MOVE_PROJECT,
                project=self.project,
                workspace=destination,
                user=self.user,
            ).exists()
        )
        self.assertTrue(
            Change.objects.filter(
                action=ActionEvents.CREATE_WORKSPACE,
                workspace=destination,
                user=self.user,
            ).exists()
        )

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_site_migration_shared_workspace_keeps_explicit_ownership(self) -> None:
        self.project.add_user(self.anotheruser, "Administration")
        Project.objects.filter(pk=self.project.pk).update(workspace=None)
        other = Project.objects.create(
            name="Second shared project", slug="second-shared"
        )
        data = {
            "projects": [self.project.pk, other.pk],
            "destination": "shared",
            "name": "Shared workspace",
        }
        url = reverse("manage-github-migration", args=["github.com"])

        response = self.client.get(url)
        for project in (self.project, other):
            self.assertContains(response, f"{project.name} ({project.slug})")
        self.assertRedirects(self.client.post(url, data), url)
        workspace = Workspace.objects.get(name="Shared workspace")
        self.assertCountEqual(
            workspace.projects.values_list("pk", flat=True), [self.project.pk, other.pk]
        )
        self.assertEqual(
            list(workspace.get_owners_group().user_set.values_list("pk", flat=True)),
            [self.user.pk],
        )
        self.assertContains(self.client.post(url, data), "Select a valid choice")
        self.assertEqual(Workspace.objects.filter(name="Shared workspace").count(), 1)

    def test_site_migration_disables_workspace_creation_with_billing(self) -> None:
        url = reverse("manage-github-migration", args=["github.com"])
        self.assertContains(
            self.client.get(url),
            "Workspace creation on this site is managed through billing.",
        )
        self.assertEqual(
            self.client.post(
                url, {"projects": [self.project.pk], "destination": "separate"}
            ).status_code,
            403,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_workspace_bulk_migration_confirms_and_detects_replay(self) -> None:
        connections = reverse("workspace-integrations", args=[self.workspace.pk])
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        self.assertNotContains(self.client.get(connections), url)
        self._setup_migratable_component()
        self.assertContains(self.client.get(connections), url)

        self.project.add_user(self.anotheruser, "Administration")
        self.client.force_login(self.anotheruser)
        response = self.client.get(url)
        self.assertEqual(
            [item.pk for item in response.context["components"]], [self.component.pk]
        )
        preview = response.context["preview"]
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")

        self.client.force_login(self.user)
        self.assertRedirects(self.client.post(url, {"preview": preview}), connections)
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")

        self.client.force_login(self.anotheruser)
        self.assertRedirects(self.client.post(url, {"preview": preview}), connections)
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "github-app")
        self.assertContains(
            self.client.post(url, {"preview": preview}, follow=True),
            "no longer eligible",
        )
        self.assertNotContains(self.client.get(connections), url)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_workspace_bulk_migration_skips_changed_repository(self) -> None:
        self._setup_migratable_component()
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        preview = self.client.get(url).context["preview"]
        GitHubInstallation.objects.filter(workspace=self.workspace).update(
            repositories=[_repo_entry("test-org/repo1"), _repo_entry("test-org/repo2")]
        )
        Component.objects.filter(pk=self.component.pk).update(
            repo="git@github.com:test-org/repo2.git"
        )

        self.assertContains(
            self.client.post(url, {"preview": preview}, follow=True),
            "no longer eligible",
        )
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_workspace_bulk_migration_skips_component_moved_between_projects(
        self,
    ) -> None:
        self._setup_migratable_component()
        destination = Project.objects.create(
            name="Another project", slug="another-project", workspace=self.workspace
        )
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        preview = self.client.get(url).context["preview"]
        Component.objects.filter(pk=self.component.pk).update(project=destination)

        response = self.client.post(url, {"preview": preview}, follow=True)

        self.assertContains(response, "no longer eligible")
        self.component.refresh_from_db()
        self.assertEqual(self.component.project_id, destination.pk)
        self.assertEqual(self.component.vcs, "git")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_workspace_bulk_migration_preserves_new_repository_settings(self) -> None:
        self._setup_migratable_component()
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])

        for field, value in (
            ("push", "git@github.com:fork/repo1.git"),
            ("push_branch", "translations"),
            ("vcs_params", {"git_force_push": True}),
        ):
            with self.subTest(field=field):
                preview = self.client.get(url).context["preview"]
                Component.objects.filter(pk=self.component.pk).update(**{field: value})

                self.assertContains(
                    self.client.post(url, {"preview": preview}, follow=True),
                    "no longer eligible",
                )
                self.component.refresh_from_db()
                self.assertEqual(self.component.vcs, "git")
                self.assertEqual(getattr(self.component, field), value)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_site_bulk_migration_is_app_scoped_and_capped(self) -> None:
        self._setup_migratable_component()
        self._make_credentials(hostname="github.example.com", app_id="123")
        url = reverse("manage-github-bulk-migration", args=["github.com"])
        other_url = reverse("manage-github-bulk-migration", args=["github.example.com"])
        preview = self.client.get(url).context["preview"]
        self.assertTrue(preview)
        self.assertContains(self.client.get(other_url), "No components are ready")
        self.assertRedirects(
            self.client.post(other_url, {"preview": preview}),
            reverse("manage-github-migration", args=["github.example.com"]),
        )
        with patch("weblate.vcs.views.MIGRATION_BATCH_SIZE", 1):
            second = self.create_po(
                project=self.project, name="Second legacy component"
            )
            Component.objects.filter(pk=second.pk).update(
                vcs="git", repo="https://git.example.org/team/github.com-mirror.git"
            )
            response = self.client.get(url)
            self.assertContains(response, "Migrate these components")
            self.assertEqual(
                [component.pk for component in response.context["components"]],
                [self.component.pk],
            )
            Component.objects.filter(pk=second.pk).update(
                repo="https://api.github.com/test-org/repo1.git"
            )
            self.assertContains(
                self.client.get(url), "More than 1 candidate components"
            )
            workspace = self.client.get(
                reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
            )
            self.assertTrue(workspace.context["has_more"])
            self.assertEqual(len(workspace.context["components"]), 1)

    def test_bulk_confirmation_avoids_lock_after_losing_edit_access(self) -> None:
        self._setup_migratable_component()
        self.workspace.add_owner(self.anotheruser)
        self.project.add_user(self.anotheruser, "Administration")
        destination = Project.objects.create(
            name="Private destination",
            slug="private-migration-destination",
            workspace=self.workspace,
            access_control=Project.ACCESS_PRIVATE,
        )
        self.client.force_login(self.anotheruser)
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        preview = self.client.get(url).context["preview"]
        self.assertTrue(preview)
        Component.objects.filter(pk=self.component.pk).update(project=destination)

        with patch.object(Component, "locked_for_update") as lock:
            response = self.client.post(url, {"preview": preview}, follow=True)

        lock.assert_not_called()
        self.assertContains(response, "no longer eligible")
        self.assertNotContains(response, destination.slug)
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_bulk_confirmation_rechecks_edit_access_after_lock(self) -> None:
        self._setup_migratable_component()
        self.workspace.add_owner(self.anotheruser)
        self.project.add_user(self.anotheruser, "Administration")
        self.client.force_login(self.anotheruser)
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        preview = self.client.get(url).context["preview"]
        self.assertTrue(preview)

        response = self._migrate_with_concurrent_change(
            url,
            lambda: self.project.remove_user(self.anotheruser),
            data={"preview": preview},
        )

        self.assertRedirects(
            response,
            reverse("workspace-integrations", args=[self.workspace.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            ["One component was no longer eligible for migration."],
        )
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_bulk_confirmation_rechecks_workspace_after_lock(self) -> None:
        self._setup_migratable_component()
        Component.objects.filter(pk=self.component.pk).update(
            push="git@github.com:fork/repo1.git", push_branch="translations"
        )
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        preview = self.client.get(url).context["preview"]
        destination = Workspace.objects.create(name="Workspace without a connection")

        def move_before_lock(project_ids, *, exclusive):
            Project.objects.filter(pk=self.project.pk).update(workspace=destination)
            lock_check_projects(project_ids, exclusive=exclusive)

        with patch(
            "weblate.checks.locks.lock_check_projects", side_effect=move_before_lock
        ) as boundary_lock:
            response = self.client.post(url, {"preview": preview}, follow=True)

        boundary_lock.assert_called_once_with({self.project.pk}, exclusive=False)
        self.assertContains(response, "no longer eligible")
        self.component.refresh_from_db()
        self.assertEqual(self.component.project.workspace_id, destination.pk)
        self.assertEqual(self.component.vcs, "git")
        self.assertEqual(self.component.push, "git@github.com:fork/repo1.git")
        self.assertEqual(self.component.push_branch, "translations")

    def test_bulk_previews_batch_inventories_and_breadcrumb_queries(self) -> None:
        self._setup_migratable_component()
        workspace = Workspace.objects.create(name="Second migration workspace")
        project = Project.objects.create(
            name="Second migration project",
            slug="second-migration",
            workspace=workspace,
        )
        second = self.create_po(project=project, name="Second migration component")
        Component.objects.filter(pk=second.pk).update(
            vcs="git", repo="git@github.com:other-org/repo2.git"
        )
        GitHubInstallation.objects.create(
            workspace=workspace,
            installation_id="23456",
            target_login="other-org",
            repositories=[_repo_entry("other-org/repo2")],
        )
        for component in (self.component, second):
            root = Category.objects.create(
                project=component.project, name="Root", slug="root"
            )
            parent = Category.objects.create(
                project=component.project, category=root, name="Parent", slug="parent"
            )
            nested = Category.objects.create(
                project=component.project, category=parent, name="Nested", slug="nested"
            )
            Component.objects.filter(pk=component.pk).update(category=nested)
        url = reverse("manage-github-bulk-migration", args=["github.com"])

        breadcrumbs = Template(
            "{% load translations %}{% path_object_links component flags=False %}"
        )

        def render_preview(request, template_name, context):
            # Check before the page template can populate the relation caches.
            with self.assertNumQueries(0):
                for component in context["components"]:
                    links = breadcrumbs.render(Context({"component": component}))
                    self.assertIn("/root/parent/nested/", links)
                    self.assertIn(component.project.workspace.get_absolute_url(), links)
            return render(request, template_name, context)

        with patch("weblate.vcs.views.render", side_effect=render_preview):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url)
            inventory_queries = [
                query
                for query in queries.captured_queries
                if '"vcs_installation"."repositories"' in query["sql"]
            ]
            workspace_preview = self.client.get(
                reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            [component.pk for component in response.context["components"]],
            [self.component.pk, second.pk],
        )
        self.assertEqual(len(inventory_queries), 1)
        self.assertEqual(workspace_preview.status_code, 200)
        self.assert_integration_markup(response, ["h2"])
        self.assert_integration_markup(workspace_preview, ["h2"])
        self.assertEqual(
            [component.pk for component in workspace_preview.context["components"]],
            [self.component.pk],
        )

    @http_mock.activate
    def test_site_migration_install_returns_to_filtered_checklist(self) -> None:
        search = "https://outside.example/?query=test"
        self.workspace.name = f"Workspace {search}"
        self.workspace.save(update_fields=["name"])
        query = {"q": search, "unconnected_page": "1"}
        checklist = reverse("manage-github-migration", args=["github.com"], query=query)
        page = self.client.get(
            reverse("manage-github-migration", args=["github.com"]),
            {**query, "next": "https://outside.example/"},
        )
        self.assert_integration_markup(page, ["h2", "h3", "h3", "h3"])
        [(workspace, start)] = page.context["unconnected"]
        self.assertEqual(workspace.pk, self.workspace.pk)
        self.assertEqual(parse_qs(urlparse(start).query)["next"], [checklist])
        response = self.client.get(start)
        [state] = parse_qs(urlparse(response["Location"]).query)["state"]
        self._mock_oauth()
        self._mock_setup_api()
        response = self.client.get(
            reverse("github-app-setup"),
            {"installation_id": "12345", "state": state, "code": "oauth-code"},
        )
        self.assertRedirects(response, checklist)
        self.assertTrue(
            GitHubInstallation.objects.filter(
                installation_id="12345", workspace=self.workspace
            ).exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_workspace_bulk_migration_continues_after_failed_component(self) -> None:
        self._setup_migratable_component()
        second = self.create_po(project=self.project, name="Second legacy component")
        Component.objects.filter(pk=second.pk).update(
            vcs="git", repo="git@github.com:test-org/repo1.git"
        )
        url = reverse("workspace-github-bulk-migration", args=[self.workspace.pk])
        preview = self.client.get(url).context["preview"]
        with patch.object(
            GithubAppRepository,
            "validate_component",
            side_effect=[ValidationError("Test validation error."), None],
        ):
            response = self.client.post(url, {"preview": preview}, follow=True)
        self.assertContains(response, "Test validation error.")
        self.assertContains(response, "Migrated one component")
        self.component.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")
        self.assertEqual(second.vcs, "github-app")

    def test_connection_pagination_preserves_app_filter(self) -> None:
        for index in range(3):
            GitHubInstallation.objects.create(
                workspace=self.workspace,
                installation_id=str(index + 1),
                target_login=f"org-{index}",
            )
        GitHubInstallation.objects.create(
            workspace=self.workspace,
            hostname="github.example.com",
            installation_id="4",
            target_login="stale-account",
            enabled=False,
        )
        with patch("weblate.vcs.views.LIST_PAGE_SIZE", 2):
            response = self.client.get(
                reverse(
                    "manage-github-connections", query={"host": "github.com", "page": 2}
                )
            )
        self.assertContains(response, "org-0")
        self.assertNotContains(response, "stale-account")
        self.assert_integration_markup(response, ["h2"])
        self.assertContains(
            self.client.get(reverse("manage-github-connections")), "stale-account"
        )

    def test_repository_pagination_preserves_category_target(self) -> None:
        category = Category.objects.create(
            project=self.project, name="Category", slug="category"
        )
        first = _repo_entry("test-org/aaa")
        second = _repo_entry("test-org/bbb")
        installation = GitHubInstallation.objects.create(
            workspace=self.workspace,
            installation_id="12345",
            target_login="test-org",
            repositories=[
                first,
                _repo_entry("test-org/archived", archived=True),
                second,
                _repo_entry("test-org/ccc"),
            ],
        )
        other_repo = _repo_entry("zzz-org/only-repo")
        other_installation = GitHubInstallation.objects.create(
            workspace=self.workspace,
            installation_id="23456",
            target_login="zzz-org",
            repositories=[other_repo],
        )
        url = reverse("github-app-repositories")
        query = {
            "workspace": str(self.workspace.pk),
            "project": str(self.project.pk),
            "category": str(category.pk),
        }
        with patch("weblate.vcs.views.LIST_PAGE_SIZE", 1):
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(url, {**query, "page": "2"})
            inventory_queries = [
                row["sql"]
                for row in queries.captured_queries
                if '"vcs_installation"."repositories"' in row["sql"]
            ]
            self.assertEqual(len(inventory_queries), 1)
            self.assertIn("LIMIT 1", inventory_queries[0])
            document = BeautifulSoup(response.content, "html.parser")
            [account_link] = document.select('nav[aria-label="Connected accounts"] a')
            href = account_link["href"]
            assert isinstance(href, str)
            self.assertEqual(
                parse_qs(urlparse(href).query),
                {
                    **{key: [value] for key, value in query.items()},
                    "accounts_page": ["2"],
                },
            )
            next_account = self.client.get(f"{url}{href}")
        self.assertContains(
            response,
            _import_url(
                installation, second, project=self.project.pk, category=category.pk
            ).replace("&", "&amp;"),
        )
        self.assertNotContains(response, "test-org/aaa")
        self.assertNotContains(response, other_repo["full_name"])
        self.assertContains(response, f"category={category.pk}")
        self.assertContains(
            next_account,
            _import_url(
                other_installation,
                other_repo,
                project=self.project.pk,
                category=category.pk,
            ).replace("&", "&amp;"),
        )
        self.assertNotContains(next_account, second["full_name"])
        self.assertEqual(next_account.context["page_obj"].number, 1)
        self.assertCountEqual(
            [
                link["aria-label"]
                for link in document.select(".pagination a[href][aria-label]")
            ],
            ["First page", "Previous page", "Next page", "Last page"],
        )

    def _migrate_with_concurrent_change(self, url, change, *, data=None):
        """POST the migration form, applying ``change`` just before each lock."""
        original_locked_for_update = Component.locked_for_update

        @contextmanager
        def locked_for_update(component, **kwargs):
            change()
            with original_locked_for_update(component, **kwargs) as locked:
                yield locked

        if data is None:
            data = {"components": [str(self.component.pk)]}
        with patch.object(Component, "locked_for_update", locked_for_update):
            return self.client.post(url, data)

    def _setup_migratable_component(self):
        GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[_repo_entry("test-org/repo1")],
        )
        Component.objects.filter(pk=self.component.pk).update(
            vcs="git",
            repo="git@github.com:test-org/repo1.git",
        )
        return reverse(
            "github-app-migration", kwargs={"workspace_id": self.workspace.pk}
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_migration_skips_component_moved_out_of_workspace(self) -> None:
        url = self._setup_migratable_component()

        response = self._migrate_with_concurrent_change(
            url,
            lambda: Project.objects.filter(pk=self.project.pk).update(workspace=None),
        )

        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("no longer eligible", response_messages[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_migration_skips_component_pointed_elsewhere(self) -> None:
        url = self._setup_migratable_component()

        response = self._migrate_with_concurrent_change(
            url,
            lambda: Component.objects.filter(pk=self.component.pk).update(
                repo="git@github.com:test-org/other.git"
            ),
        )

        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("no longer eligible", response_messages[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_migration_reports_validation_error(self) -> None:
        url = self._setup_migratable_component()

        with patch.object(
            GithubAppRepository,
            "validate_component",
            side_effect=ValidationError("Repository is not available."),
        ):
            response = self.client.post(url, {"components": [str(self.component.pk)]})

        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.component.refresh_from_db()
        self.assertEqual(self.component.vcs, "git")
        response_messages = [
            str(message) for message in get_messages(response.wsgi_request)
        ]
        self.assertEqual(len(response_messages), 1)
        self.assertIn("Repository is not available.", response_messages[0])
        self.assertIn(self.component.full_slug, response_messages[0])


class GitHubAppAccessControlTest(ViewTestCase):
    """Permission checks for the GitHub App connect/import views."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(
            mock_dns("api.github.com", "github.com", "github.example.com")
        )
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
        http_mock.register(
            "POST",
            "https://github.com/login/oauth/access_token",
            json={"access_token": "ghu_user", "token_type": "bearer"},
        )
        http_mock.register(
            "GET",
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
        http_mock.register(
            "GET",
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
        http_mock.register(
            "GET",
            "https://api.github.com/app/installations/12345",
            json={
                "id": 12345,
                "account": {"login": "test-org", "type": "Organization"},
            },
        )
        http_mock.register(
            "POST",
            "https://api.github.com/app/installations/12345/access_tokens",
            json={"token": "ghs_test"},
        )
        http_mock.register(
            "GET",
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

    def test_policy_restricted_project_targets(self) -> None:
        repo = _repo_entry("test-org/repo1")
        installation = GitHubInstallation.objects.create(
            installation_id="12345",
            target_type="Organization",
            target_login="test-org",
            workspace=self.workspace,
            repositories=[repo],
        )
        category = Category.objects.create(
            project=self.project, name="Category", slug="category"
        )
        self.project.add_user(self.other_user, "Administration")
        self.client.login(username=self.other_user.username, password="testpassword")
        self.assertContains(
            self.client.get(reverse("github-app-repositories")), "test-org/repo1"
        )
        for restriction in ("block", "two-factor"):
            if restriction == "block":
                block = UserBlock.objects.create(
                    user=self.other_user, project=self.project
                )
            else:
                self.project.enforced_2fa = True
                self.project.save(update_fields=["enforced_2fa"])
            for workspace_access in (False, True):
                if workspace_access:
                    self.workspace.add_owner(self.other_user)
                with self.subTest(
                    restriction=restriction, workspace_access=workspace_access
                ):
                    self.assertEqual(
                        self.client.get(reverse("github-app-repositories")).status_code,
                        200 if workspace_access else 403,
                    )
                    self.assertEqual(
                        self.client.get(
                            reverse("github-app-repositories"),
                            {"project": self.project.pk},
                        ).status_code,
                        403,
                    )
                    for target in (
                        {"project": self.project.pk},
                        {"category": category.pk},
                    ):
                        response = self.client.get(
                            _import_url(installation, repo, **target)
                        )
                        self.assertEqual(response.status_code, 403)
                    self.assertNotIn("session_component", self.client.session)
            self.other_user.remove_team(None, self.workspace.get_owners_group())
            if restriction == "block":
                block.delete()

    def test_install_requires_login(self) -> None:
        self.client.logout()
        response = self.client.get(
            reverse("github-app-install"),
            {"workspace": str(self.workspace.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_migration_requires_workspace_access(self) -> None:
        self.client.login(username=self.other_user.username, password="testpassword")

        response = self.client.get(
            reverse(
                "github-app-migration",
                kwargs={"workspace_id": self.workspace.pk},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_setup_requires_login(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("github-app-setup"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_setup_denied_for_user_managing_a_different_workspace(self) -> None:
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

    @http_mock.activate
    def test_workspace_member_can_import_repo_linked_by_other_user(self) -> None:
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
        self.enterContext(
            mock_dns("api.github.com", "github.com", "github.example.com")
        )
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
        user.clear_permissions_cache()

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

    def test_register_submit_posts_directly_to_github_with_csp(self) -> None:
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

    def test_register_submit_rejects_invalid_host(self) -> None:
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

    def test_register_rejects_prefilled_invalid_host(self) -> None:
        response = self.client.get(
            reverse("github-app-register"),
            {"host": "github.com@attacker.example"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["hostname"], "github.com")
        self.assertNotContains(response, "attacker.example")

    def test_register_post_sends_expected_manifest_to_github(self) -> None:
        url, manifest = self._capture_github_call(
            host="github.com", name="My Weblate", public="1"
        )

        # Destination of the cross-origin POST GitHub receives.
        self.assertTrue(url.startswith("https://github.com/settings/apps/new?"))
        self.assertIn("state", parse_qs(urlparse(url).query))

        # Body parameters GitHub uses to create the App.
        self.assertEqual(manifest["name"], "My Weblate")
        self.assertEqual(manifest["url"], get_site_url())
        # The webhook carries an opaque per-App token, so assert its
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
        self.assertIn("repository", manifest["default_events"])
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

    @override_settings(SITE_TITLE="Acme Translate")
    def test_register_default_name_uses_site_title(self) -> None:
        response = self.client.get(reverse("github-app-register"))

        self.assertEqual(response.context["name"], "Acme Translate (testserver)")
        manifest = json.loads(response.context["manifest_json"])
        self.assertEqual(manifest["name"], "Acme Translate (testserver)")

    @http_mock.activate
    def test_register_callback_stores_credentials(self) -> None:
        http_mock.register(
            "POST",
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
        self.assertEqual(len(http_mock.calls), 1)
        self.assertEqual(
            http_mock.calls[0].request.url,
            "https://api.github.com/app-manifests/tempcode123/conversions",
        )
        credentials = GitHubAppCredentials.objects.get(hostname="github.com")
        self.assertEqual(credentials.app_id, "4242")
        self.assertEqual(credentials.app_slug, "weblate-auto")
        self.assertEqual(credentials.webhook_secret, "fresh-secret")
        self.assertEqual(credentials.client_id, "Iv1.manifestclientid")
        self.assertEqual(credentials.client_secret, "manifest-client-secret")
        self.assertIn("manifest", credentials.private_key)

    @http_mock.activate
    def test_register_callback_quotes_code_path_segment(self) -> None:
        http_mock.register(
            "POST",
            "https://api.github.com/app-manifests/"
            "..%2Finstallations%2F123%2Faccess_tokens/conversions",
            json=MANIFEST_RESPONSE,
        )
        submit = self._post_register(host="github.com")
        state = parse_qs(urlparse(self._action_url(submit)).query)["state"][0]

        response = self.client.get(
            reverse("github-app-register-callback"),
            {
                "code": "../installations/123/access_tokens",
                "state": state,
            },
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertTrue(GitHubAppCredentials.objects.exists())
        self.assertEqual(
            http_mock.calls[0].request.url,
            "https://api.github.com/app-manifests/"
            "..%2Finstallations%2F123%2Faccess_tokens/conversions",
        )

    @http_mock.activate
    def test_register_callback_updates_existing(self) -> None:
        http_mock.register(
            "POST",
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

    @http_mock.activate
    def test_register_callback_reject(self) -> None:
        response = self.client.get(reverse("github-app-register-callback"))

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

        response = self.client.get(
            reverse("github-app-register-callback"),
            {"code": "x", "state": "tampered"},
        )

        self.assertRedirects(response, reverse("manage-github-accounts"))
        self.assertFalse(GitHubAppCredentials.objects.exists())

        http_mock.register(
            "POST",
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

    def test_register_requires_management_configure(self) -> None:
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

    def test_remove_app_requires_management_configure(self) -> None:
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

    def test_register_form_warns_about_existing_host(self) -> None:
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

    def test_register_truncates_long_names(self) -> None:
        long_name = "x" * 100
        _url, manifest = self._capture_github_call(host="github.com", name=long_name)
        # GitHub rejects names longer than 34 chars, so the manifest body must
        # already be truncated to the limit.
        self.assertEqual(manifest["name"], "x" * 34)

    def test_credentials_page_renders_remove_app_modal(self) -> None:
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

    def test_credentials_page_disables_remove_app_with_connected_accounts(self) -> None:
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
        self.assertContains(response, "Remove connected accounts first.")
        self.assertNotContains(
            response,
            f'data-bs-target="#remove-app-{credentials.pk}"',
        )
        self.assertNotContains(
            response,
            f'action="{reverse("manage-github-app-remove", kwargs={"pk": credentials.pk})}"',
        )

    def test_credentials_page_lists_registered_apps(self) -> None:
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

    def test_credentials_remove_app_credentials(self) -> None:
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

    def test_credentials_remove_app_credentials_rejects_connected_accounts(
        self,
    ) -> None:
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
