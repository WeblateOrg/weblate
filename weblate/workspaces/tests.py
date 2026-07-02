# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.http import Http404
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import Group
from weblate.billing.models import Billing, BillingQuerySet
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Project
from weblate.trans.templatetags.translations import get_breadcrumbs
from weblate.trans.tests.test_models import BaseTestCase
from weblate.trans.tests.utils import (
    create_another_user,
    create_test_billing,
    create_test_user,
)
from weblate.utils.views import UnsupportedPathObjectError, parse_path
from weblate.workspaces.models import WORKSPACE_PROJECT_CREATORS_GROUP, Workspace


class WorkspaceViewTest(BaseTestCase):
    def create_project(
        self,
        workspace: Workspace,
        *,
        name: str,
        slug: str,
        access_control: int = Project.ACCESS_PUBLIC,
        source_review: bool = False,
        translation_review: bool = False,
    ) -> Project:
        return Project.objects.create(
            name=name,
            slug=slug,
            web="https://example.com/",
            workspace=workspace,
            access_control=access_control,
            source_review=source_review,
            translation_review=translation_review,
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

    def test_workspace_project_sort_does_not_affect_search_sort(self) -> None:
        workspace = Workspace.objects.create(name="Test workspace")
        self.create_project(
            workspace,
            name="Visible project",
            slug="visible-project",
        )

        response = self.client.get(workspace.get_absolute_url(), {"sort_by": "name"})

        self.assertEqual(response.context["projects"].paginator.sort_by, "name")
        self.assertEqual(
            response.context["search_form"].sort_query, "component,-priority"
        )

    def test_workspace_project_listing_shows_review_columns(self) -> None:
        workspace = Workspace.objects.create(name="Review workspace")
        self.create_project(
            workspace,
            name="Review project",
            slug="review-project",
            translation_review=True,
        )

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, "Approved")
        self.assertContains(response, "Unreviewed")

    def test_workspace_project_listing_hides_review_columns(self) -> None:
        workspace = Workspace.objects.create(name="No review workspace")
        self.create_project(
            workspace,
            name="No review project",
            slug="no-review-project",
        )

        response = self.client.get(workspace.get_absolute_url())

        self.assertNotContains(response, "Unreviewed", status_code=200)

    def test_workspace_project_listing_ignores_hidden_review_projects(self) -> None:
        workspace = Workspace.objects.create(name="Hidden review workspace")
        self.create_project(
            workspace,
            name="Visible no review project",
            slug="visible-no-review-project",
        )
        self.create_project(
            workspace,
            name="Hidden review project",
            slug="hidden-review-project",
            access_control=Project.ACCESS_PRIVATE,
            translation_review=True,
        )

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, "Visible no review project")
        self.assertNotContains(response, "Hidden review project", status_code=200)
        self.assertNotContains(response, "Unreviewed", status_code=200)

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

    def test_workspace_settings_are_visible_to_workspace_owner(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Settings workspace")
        workspace.add_owner(user)
        settings_url = reverse("settings", kwargs={"path": workspace.get_url_path()})
        integrations_url = f"{reverse('account-vcs')}?workspace={workspace.pk}"

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, settings_url)
        self.assertContains(response, integrations_url)
        self.assertNotContains(response, 'data-bs-target="#settings"', status_code=200)

        response = self.client.get(settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], workspace)

    @override_settings(DEFAULT_COMMIT_MESSAGE="Site default workspace commit")
    def test_workspace_settings_show_site_default_message_control(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Settings workspace")
        workspace.add_owner(user)

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(
            reverse("settings", kwargs={"path": workspace.get_url_path()})
        )

        self.assertContains(
            response, 'data-site-default-value="Site default workspace commit"'
        )
        self.assertContains(response, "Restore site default")

    def test_workspace_settings_are_hidden_without_workspace_edit(self) -> None:
        workspace = Workspace.objects.create(name="Public workspace")
        self.create_project(
            workspace,
            name="Public project",
            slug="public-project",
        )
        settings_url = reverse("settings", kwargs={"path": workspace.get_url_path()})

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, "Public project")
        self.assertNotContains(response, settings_url, status_code=200)
        self.assertNotContains(response, 'data-bs-target="#settings"', status_code=200)

    def test_workspace_settings_update_name_as_workspace_owner(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Original view workspace")
        workspace.add_owner(user)
        settings_url = reverse("settings", kwargs={"path": workspace.get_url_path()})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.post(settings_url, {"name": "Renamed view workspace"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], settings_url)
        workspace.refresh_from_db()
        self.assertEqual(workspace.name, "Renamed view workspace")
        change = workspace.change_set.get(action=ActionEvents.WORKSPACE_SETTING_CHANGE)
        self.assertEqual(change.user, user)
        self.assertEqual(change.details["field"], "name")

    def test_workspace_settings_update_denied_without_workspace_edit(self) -> None:
        workspace = Workspace.objects.create(name="Read-only workspace")
        self.create_project(
            workspace,
            name="Read-only project",
            slug="read-only-project",
        )
        user = create_another_user()

        self.client.login(username=user.username, password="testpassword")
        response = self.client.post(
            reverse("settings", kwargs={"path": workspace.get_url_path()}),
            {"name": "Denied workspace"},
        )

        self.assertEqual(response.status_code, 404)
        workspace.refresh_from_db()
        self.assertEqual(workspace.name, "Read-only workspace")

    def test_empty_billing_workspace_is_visible_to_workspace_owner(self) -> None:
        user = create_test_user()
        billing = create_test_billing(user, invoice=False)

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(billing.workspace.get_absolute_url())

        self.assertContains(response, billing.workspace.name)
        self.assertContains(
            response, f"{reverse('create-project')}?workspace={billing.workspace_id}"
        )
        self.assertContains(response, "Add new translation project")
        self.assertContains(response, billing.get_absolute_url())
        self.assertNotContains(response, 'data-bs-target="#billing"', status_code=200)
        self.assertNotContains(response, "Billing plan", status_code=200)

    def test_empty_billing_workspace_project_url_checks_current_billing(self) -> None:
        user = create_test_user()
        billing = create_test_billing(user, invoice=False)
        other = Billing.objects.create(plan=billing.plan)
        other.workspace.add_owner(user)
        self.create_project(
            other.workspace,
            name="Other billed project",
            slug="other-billed-project",
        )

        self.client.login(username=user.username, password="testpassword")
        with patch.object(
            BillingQuerySet,
            "for_user_within_limits",
            side_effect=AssertionError,
        ):
            response = self.client.get(billing.workspace.get_absolute_url())

        self.assertContains(response, billing.workspace.name)
        self.assertContains(
            response, f"{reverse('create-project')}?workspace={billing.workspace_id}"
        )

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

    def test_workspace_url_path_parsing(self) -> None:
        workspace = Workspace.objects.create(name="Path workspace")

        self.assertEqual(
            workspace.get_url_path(), ("-", "workspace", str(workspace.pk))
        )
        self.assertEqual(
            parse_path(None, workspace.get_url_path(), (Workspace,)), workspace
        )

    def test_workspace_url_path_requires_opt_in(self) -> None:
        workspace = Workspace.objects.create(name="Unsupported path workspace")

        with self.assertRaises(UnsupportedPathObjectError):
            parse_path(None, workspace.get_url_path(), (Project,))

    def test_workspace_with_deferred_name_does_not_eager_load(self) -> None:
        workspace = Workspace.objects.create(name="Deferred workspace")

        deferred = Workspace.objects.only("id").get(pk=workspace.pk)

        self.assertEqual(deferred.pk, workspace.pk)
        self.assertIn("name", deferred.get_deferred_fields())

    def test_workspace_url_path_rejects_invalid_uuid(self) -> None:
        with self.assertRaisesMessage(Http404, "Invalid workspace id"):
            parse_path(None, ("-", "workspace", "not-a-uuid"), (Workspace,))

    def test_workspace_name_change_history(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Original workspace")

        workspace.acting_user = user
        workspace.name = "Renamed workspace"
        workspace.save()

        change = workspace.change_set.get(action=ActionEvents.WORKSPACE_SETTING_CHANGE)
        self.assertEqual(change.user, user)
        self.assertEqual(change.path_object, workspace)
        self.assertEqual(change.get_absolute_url(), workspace.get_absolute_url())
        self.assertEqual(change.details["field"], "name")
        self.assertEqual(change.details["old"], "Original workspace")
        self.assertEqual(change.details["target"], "Renamed workspace")
        self.assertEqual(
            change.get_details_display(),
            'Workspace name changed from "Original workspace" to "Renamed workspace".',
        )

    def test_workspace_history_tab_shows_changes(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Original tab workspace")
        workspace.add_owner(user)
        workspace.acting_user = user
        workspace.name = "Renamed tab workspace"
        workspace.save()

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#history"')
        self.assertContains(response, "Insights")
        self.assertContains(response, "Failing checks")
        self.assertContains(response, "Workspace name changed")
        self.assertContains(response, "Browse all workspace changes")
        self.assertContains(
            response, reverse("changes", kwargs={"path": workspace.get_url_path()})
        )
        self.assertContains(
            response, reverse("checks", kwargs={"path": workspace.get_url_path()})
        )

    def test_workspace_history_tab_shows_project_changes(self) -> None:
        workspace = Workspace.objects.create(name="History tab workspace")
        visible = self.create_project(
            workspace,
            name="Visible tab history project",
            slug="visible-tab-history-project",
        )
        hidden = self.create_project(
            workspace,
            name="Hidden tab history project",
            slug="hidden-tab-history-project",
            access_control=Project.ACCESS_PRIVATE,
        )
        visible.change_set.create(action=ActionEvents.CREATE_PROJECT)
        hidden.change_set.create(action=ActionEvents.CREATE_PROJECT)

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, "Visible tab history project")
        self.assertNotContains(response, "Hidden tab history project", status_code=200)

    def test_workspace_changes_include_workspace_changes(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Original browse workspace")
        workspace.add_owner(user)
        workspace.acting_user = user
        workspace.name = "Renamed browse workspace"
        workspace.save()

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(
            reverse("changes", kwargs={"path": workspace.get_url_path()})
        )

        self.assertContains(response, "Changes in Renamed browse workspace")
        self.assertContains(response, "Workspace name changed")

    def test_workspace_changes_denied_without_workspace_access(self) -> None:
        workspace = Workspace.objects.create(name="Denied history workspace")
        self.create_project(
            workspace,
            name="Denied history project",
            slug="denied-history-project",
            access_control=Project.ACCESS_PRIVATE,
        )

        response = self.client.get(
            reverse("changes", kwargs={"path": workspace.get_url_path()})
        )

        self.assertEqual(response.status_code, 404)

    def test_workspace_changes_include_accessible_project_changes(self) -> None:
        workspace = Workspace.objects.create(name="History workspace")
        visible = self.create_project(
            workspace,
            name="Visible history project",
            slug="visible-history-project",
        )
        hidden = self.create_project(
            workspace,
            name="Hidden history project",
            slug="hidden-history-project",
            access_control=Project.ACCESS_PRIVATE,
        )
        other_workspace = Workspace.objects.create(name="Other history workspace")
        other = self.create_project(
            other_workspace,
            name="Other history project",
            slug="other-history-project",
        )
        visible.change_set.create(action=ActionEvents.CREATE_PROJECT)
        hidden.change_set.create(action=ActionEvents.CREATE_PROJECT)
        other.change_set.create(action=ActionEvents.CREATE_PROJECT)

        response = self.client.get(
            reverse("changes", kwargs={"path": workspace.get_url_path()})
        )

        self.assertContains(response, visible.name)
        self.assertNotContains(response, hidden.name, status_code=200)
        self.assertNotContains(response, other.name, status_code=200)

    def test_workspace_changes_rss(self) -> None:
        workspace = Workspace.objects.create(name="RSS workspace")
        project = self.create_project(
            workspace,
            name="RSS history project",
            slug="rss-history-project",
        )
        project.change_set.create(action=ActionEvents.CREATE_PROJECT)

        response = self.client.get(
            reverse("changes-rss", kwargs={"path": workspace.get_url_path()})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        self.assertContains(response, "Recent changes in RSS workspace")

    def test_billing_link_is_shown_to_workspace_owner(self) -> None:
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

        self.assertContains(response, billing.get_absolute_url())
        self.assertNotContains(response, 'data-bs-target="#billing"', status_code=200)
        self.assertNotContains(response, "Billing plan", status_code=200)

    def test_billing_link_is_hidden_without_billing_access(self) -> None:
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
        self.assertNotContains(response, billing.get_absolute_url(), status_code=200)

    def test_access_tab_is_shown_to_workspace_owner(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Access workspace")
        workspace.add_owner(user)
        access_url = reverse("workspace-access", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, access_url)
        self.assertNotContains(response, 'data-bs-target="#access"', status_code=200)
        self.assertNotContains(response, "Project creators", status_code=200)

        response = self.client.get(access_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], workspace)
        self.assertEqual(response.context["workspace"], workspace)

    def test_access_tab_is_hidden_without_member_management(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Project creator workspace")
        groups = workspace.setup_groups()
        user.add_team(None, groups[WORKSPACE_PROJECT_CREATORS_GROUP])
        access_url = reverse("workspace-access", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, workspace.name)
        self.assertNotContains(response, access_url, status_code=200)
        self.assertNotContains(response, 'data-bs-target="#access"', status_code=200)
        self.assertNotContains(response, "Access control", status_code=200)
        self.assertNotContains(response, "Code hosting connections", status_code=200)

        response = self.client.get(access_url)

        self.assertEqual(response.status_code, 404)

    def test_workspace_team_names_are_unique(self) -> None:
        workspace = Workspace.objects.create(name="Team workspace")
        workspace.setup_groups()

        with self.assertRaisesMessage(
            ValidationError, "A team with this name already exists in this workspace."
        ):
            Group.objects.create(name="Owners", defining_workspace=workspace)

    def test_workspace_teams_use_all_languages(self) -> None:
        workspace = Workspace.objects.create(name="Language workspace")

        groups = workspace.setup_groups()

        self.assertEqual(
            groups[WORKSPACE_PROJECT_CREATORS_GROUP].language_selection, SELECTION_ALL
        )

    def test_workspace_team_save_normalizes_languages(self) -> None:
        workspace = Workspace.objects.create(name="Saved language workspace")
        group = Group.objects.create(name="Team", defining_workspace=workspace)
        Group.objects.filter(pk=group.pk).update(language_selection=SELECTION_MANUAL)

        group.refresh_from_db()
        group.name = "Renamed team"
        group.save(update_fields=["name"])

        group.refresh_from_db()
        self.assertEqual(group.language_selection, SELECTION_ALL)
