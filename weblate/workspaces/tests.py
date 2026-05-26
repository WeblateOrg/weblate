# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.urls import reverse

from weblate.trans.models import Project
from weblate.trans.templatetags.translations import get_breadcrumbs
from weblate.trans.tests.test_models import BaseTestCase
from weblate.trans.tests.utils import (
    create_another_user,
    create_test_billing,
    create_test_user,
)
from weblate.utils.views import parse_path
from weblate.workspaces.models import Workspace


class WorkspaceViewTest(BaseTestCase):
    def create_project(
        self,
        workspace: Workspace,
        *,
        name: str,
        slug: str,
        access_control: int = Project.ACCESS_PUBLIC,
    ) -> Project:
        return Project.objects.create(
            name=name,
            slug=slug,
            web="https://example.com/",
            workspace=workspace,
            access_control=access_control,
        )

    def test_workspace_lists_accessible_projects(self) -> None:
        workspace = Workspace.objects.create(name="Test workspace")
        visible = self.create_project(
            workspace,
            name="Visible project",
            slug="visible-project",
        )
        hidden = self.create_project(
            workspace,
            name="Hidden project",
            slug="hidden-project",
            access_control=Project.ACCESS_PRIVATE,
        )

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, visible.name)
        self.assertNotContains(response, hidden.name, status_code=200)

    def test_workspace_without_accessible_projects_is_not_visible(self) -> None:
        workspace = Workspace.objects.create(name="Private workspace")
        self.create_project(
            workspace,
            name="Private project",
            slug="private-project",
            access_control=Project.ACCESS_PRIVATE,
        )

        response = self.client.get(workspace.get_absolute_url())

        self.assertEqual(response.status_code, 404)

    def test_empty_workspace_is_not_visible(self) -> None:
        workspace = Workspace.objects.create(name="Empty workspace")

        response = self.client.get(workspace.get_absolute_url())

        self.assertEqual(response.status_code, 404)

    def test_empty_workspace_is_visible_to_site_admin(self) -> None:
        user = create_test_user()
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])
        workspace = Workspace.objects.create(name="Empty admin workspace")

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, workspace.name)
        self.assertNotContains(response, 'data-bs-target="#billing"', status_code=200)

    def test_empty_billing_workspace_is_visible_to_billing_owner(self) -> None:
        user = create_test_user()
        billing = create_test_billing(user, invoice=False)

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(billing.workspace.get_absolute_url())

        self.assertContains(response, billing.workspace.name)
        self.assertContains(
            response, f"{reverse('create-project')}?billing={billing.pk}"
        )
        self.assertContains(response, "Add new translation project")
        self.assertContains(response, 'data-bs-target="#billing"')
        self.assertContains(response, "Billing plan")

    def test_project_breadcrumbs_include_workspace(self) -> None:
        workspace = Workspace.objects.create(name="Breadcrumb workspace")
        project = self.create_project(
            workspace,
            name="Breadcrumb project",
            slug="breadcrumb-project",
        )
        project = parse_path(None, (project.slug,), (Project,))
        self.assertIsInstance(project, Project)

        with self.assertNumQueries(0):
            breadcrumbs = list(get_breadcrumbs(project))

        self.assertEqual(
            breadcrumbs,
            [
                (workspace.get_absolute_url(), workspace.name),
                (project.get_absolute_url(), project.name),
            ],
        )

    def test_billing_tab_is_shown_to_billing_owner(self) -> None:
        user = create_test_user()
        billing = create_test_billing(user, invoice=False)
        project = Project.objects.create(
            name="Billed project",
            slug="billed-project",
            web="https://example.com/",
            access_control=Project.ACCESS_PUBLIC,
        )
        billing.add_project(project)

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(billing.workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#billing"')
        self.assertContains(response, "Billing plan")

    def test_billing_tab_is_hidden_without_billing_access(self) -> None:
        owner = create_test_user()
        user = create_another_user()
        billing = create_test_billing(owner, invoice=False)
        project = Project.objects.create(
            name="Shared project",
            slug="shared-project",
            web="https://example.com/",
            access_control=Project.ACCESS_PUBLIC,
        )
        billing.add_project(project)

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(billing.workspace.get_absolute_url())

        self.assertContains(response, project.name)
        self.assertNotContains(response, 'data-bs-target="#billing"', status_code=200)
        self.assertNotContains(response, "Billing plan", status_code=200)
