# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import PropertyMock, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.admin import WeblateGroupAdmin
from weblate.auth.data import SELECTION_ALL, SELECTION_MANUAL
from weblate.auth.models import Group, User
from weblate.billing.models import Billing, BillingQuerySet
from weblate.lang.models import Language
from weblate.memory.models import Memory, MemoryScope
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, ComponentLink, Project
from weblate.trans.templatetags.translations import get_breadcrumbs
from weblate.trans.tests.test_models import BaseTestCase
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import (
    create_another_user,
    create_test_billing,
    create_test_user,
)
from weblate.utils.views import UnsupportedPathObjectError, parse_path
from weblate.workspaces.admin import WorkspaceAdmin
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

    def test_metric_ids_are_generated_without_replacing_uuid_primary_key(self) -> None:
        first = Workspace.objects.create(name="First metric workspace")
        second = Workspace.objects.create(name="Second metric workspace")

        self.assertNotEqual(first.metric_id, second.metric_id)
        self.assertIsInstance(first.metric_id, int)
        self.assertNotEqual(first.pk, first.metric_id)

    def test_billing_or_none_without_billing_relation(self) -> None:
        workspace = Workspace.objects.create(name="Unbilled workspace")

        with patch.object(
            Workspace,
            "billing",
            new_callable=PropertyMock,
            side_effect=AttributeError,
        ):
            self.assertIsNone(workspace.billing_or_none)

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

    def test_empty_workspace_can_be_removed_by_owner(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Removal workspace")
        workspace.add_owner(user)
        moved_project = self.create_project(
            workspace,
            name="Moved project",
            slug="moved-before-workspace-removal",
        )
        moved_project_change = Change.objects.create(
            project=moved_project,
            action=ActionEvents.CREATE_PROJECT,
        )
        workspace_change = Change.objects.create(
            workspace=workspace,
            action=ActionEvents.WORKSPACE_SETTING_CHANGE,
        )
        moved_project.workspace = None
        moved_project.save(update_fields=["workspace"])
        moved_project_change.refresh_from_db()
        self.assertEqual(moved_project_change.workspace_id, workspace.pk)

        workspace_id = workspace.pk
        workspace_group_ids = list(
            workspace.defined_groups.values_list("pk", flat=True)
        )
        remove_url = reverse("workspace-remove", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#organize"')
        self.assertContains(response, remove_url)
        self.assertContains(response, "Workspace to remove")

        response = self.client.post(
            remove_url,
            {"confirm": workspace.name},
        )

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "The workspace has been removed.")
        self.assertFalse(Workspace.objects.filter(pk=workspace_id).exists())
        self.assertFalse(Group.objects.filter(pk__in=workspace_group_ids).exists())
        moved_project_change.refresh_from_db()
        self.assertIsNone(moved_project_change.workspace_id)
        self.assertEqual(moved_project_change.project_id, moved_project.pk)
        self.assertFalse(Change.objects.filter(pk=workspace_change.pk).exists())

    def test_workspace_removal_requires_matching_name(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Confirmation workspace")
        workspace.add_owner(user)
        remove_url = reverse("workspace-remove", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.post(
            remove_url,
            {"confirm": "Wrong workspace"},
            follow=True,
        )

        self.assertContains(
            response,
            "The workspace name does not match the one marked for removal!",
        )
        self.assertTrue(Workspace.objects.filter(pk=workspace.pk).exists())

    def test_workspace_removal_is_hidden_without_workspace_edit(self) -> None:
        workspace = Workspace.objects.create(name="Protected workspace")
        project = self.create_project(
            workspace,
            name="Visible project",
            slug="visible-removal-project",
        )
        user = create_another_user()
        remove_url = reverse("workspace-remove", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(project.get_absolute_url())
        self.assertEqual(response.status_code, 200)

        response = self.client.get(workspace.get_absolute_url())

        self.assertNotContains(response, 'data-bs-target="#organize"', status_code=200)
        self.assertNotContains(response, remove_url, status_code=200)

        response = self.client.post(remove_url, {"confirm": workspace.name})

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Workspace.objects.filter(pk=workspace.pk).exists())

    def test_workspace_with_projects_can_not_be_removed(self) -> None:
        user = create_test_user()
        workspace = Workspace.objects.create(name="Project workspace")
        workspace.add_owner(user)
        self.create_project(
            workspace,
            name="Remaining project",
            slug="remaining-project",
        )
        remove_url = reverse("workspace-remove", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#organize"')
        self.assertContains(
            response,
            "The workspace cannot be removed while it contains projects.",
        )
        self.assertNotContains(response, remove_url, status_code=200)

        response = self.client.post(
            remove_url,
            {"confirm": workspace.name},
            follow=True,
        )

        self.assertContains(
            response,
            "The workspace cannot be removed while it contains projects.",
        )
        self.assertTrue(Workspace.objects.filter(pk=workspace.pk).exists())

    def test_billing_workspace_can_not_be_removed(self) -> None:
        user = create_test_user()
        billing = create_test_billing(user, invoice=False)
        workspace = billing.workspace
        remove_url = reverse("workspace-remove", kwargs={"pk": workspace.pk})

        self.client.login(username=user.username, password="testpassword")
        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#organize"')
        self.assertContains(
            response,
            "A workspace associated with billing cannot be removed.",
        )
        self.assertNotContains(response, remove_url, status_code=200)

        response = self.client.post(
            remove_url,
            {"confirm": workspace.name},
            follow=True,
        )

        self.assertContains(
            response,
            "A workspace associated with billing cannot be removed.",
        )
        self.assertTrue(Workspace.objects.filter(pk=workspace.pk).exists())

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
        self.assertNotContains(response, "Code-hosting connections", status_code=200)

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


class WorkspaceStatsTest(FixtureComponentTestCase):
    def test_workspace_stats_sum_shared_component_for_each_project(self) -> None:
        workspace = Workspace.objects.create(name="Statistics workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        shared_project = Project.objects.create(
            workspace=workspace,
            name="Shared statistics project",
            slug="shared-statistics-project",
            web="https://example.com/",
        )
        ComponentLink.objects.create(
            component=self.component,
            project=shared_project,
        )

        self.assertEqual(workspace.stats.all, self.component.stats.all * 2)
        self.assertEqual(
            workspace.stats.languages,
            self.component.translation_set.values("language_id").distinct().count(),
        )

    def test_component_sharing_refreshes_workspace_stats(self) -> None:
        workspace = Workspace.objects.create(name="Updated statistics workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        shared_project = Project.objects.create(
            workspace=workspace,
            name="Updated shared statistics project",
            slug="updated-shared-statistics-project",
            web="https://example.com/",
        )
        self.assertEqual(workspace.stats.all, self.component.stats.all)

        with self.captureOnCommitCallbacks(execute=True):
            ComponentLink.objects.create(
                component=self.component,
                project=shared_project,
            )

        refreshed = Workspace.objects.get(pk=workspace.pk)
        self.assertEqual(refreshed.stats.all, self.component.stats.all * 2)

    def test_workspace_overview_includes_inaccessible_project_stats(self) -> None:
        workspace = Workspace.objects.create(name="Overview workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        hidden = Project.objects.create(
            workspace=workspace,
            name="Hidden statistics project",
            slug="hidden-statistics-project",
            web="https://example.com/",
            access_control=Project.ACCESS_PRIVATE,
        )
        ComponentLink.objects.create(component=self.component, project=hidden)

        response = self.client.get(workspace.get_absolute_url())

        self.assertNotContains(response, hidden.name, status_code=200)
        self.assertContains(response, 'data-bs-target="#information"')
        self.assertContains(response, ">Overview</a>")
        self.assertContains(response, "String statistics")
        self.assertEqual(
            response.context["workspace"].stats.all,
            self.component.stats.all * 2,
        )

    def test_workspace_tab_order_matches_project_navigation(self) -> None:
        workspace = Workspace.objects.create(name="Navigation workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.client.login(username="testuser", password="testpassword")

        response = self.client.get(workspace.get_absolute_url())

        content = response.content
        tab_targets = [
            content.index(f'data-bs-target="#{target}"'.encode())
            for target in ("projects", "diagnostics", "information", "search")
        ]
        self.assertEqual(tab_targets, sorted(tab_targets))

    def test_project_move_schedules_workspace_stats(self) -> None:
        old_workspace = Workspace.objects.create(name="Old statistics workspace")
        new_workspace = Workspace.objects.create(name="New statistics workspace")
        self.project.workspace = old_workspace
        self.project.save(update_fields=["workspace"])

        with patch(
            "weblate.utils.tasks.update_workspace_stats.delay_on_commit"
        ) as update_workspace_stats:
            self.project.workspace = new_workspace
            self.project.save(update_fields=["workspace"])

        update_workspace_stats.assert_called_once_with(
            [str(old_workspace.pk), str(new_workspace.pk)]
        )


class WorkspaceAdminTest(BaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.site.register(Group, WeblateGroupAdmin)
        self.workspace_admin = WorkspaceAdmin(Workspace, self.site)
        self.actor = User.objects.create_user(
            "workspace-admin", "workspace-admin@example.com", "testpassword"
        )
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])

    def get_request(self):
        request = self.factory.post("/")
        request.user = self.actor
        return request

    def test_workspace_groups_do_not_block_admin_removal(self) -> None:
        workspace = Workspace.objects.create(name="Admin removal workspace")
        group_ids = list(workspace.defined_groups.values_list("pk", flat=True))

        (
            _deleted_objects,
            _model_count,
            perms_needed,
            protected,
        ) = self.workspace_admin.get_deleted_objects([workspace], self.get_request())

        self.assertNotIn("Group", perms_needed)
        self.assertEqual(protected, [])

        workspace_id = workspace.pk
        self.workspace_admin.delete_model(self.get_request(), workspace)

        self.assertFalse(Workspace.objects.filter(pk=workspace_id).exists())
        self.assertFalse(Group.objects.filter(pk__in=group_ids).exists())

    def test_workspace_admin_removal_cleans_memory_scopes(self) -> None:
        workspace = Workspace.objects.create(name="Admin memory removal workspace")
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "origin": "workspace-admin-removal",
            "status": Memory.STATUS_ACTIVE,
        }
        workspace_memory = Memory.objects.create(
            source="Workspace admin removal source",
            target="Workspace admin removal target",
            **values,
        )
        mixed_memory = Memory.objects.create(
            source="Mixed workspace admin removal source",
            target="Mixed workspace admin removal target",
            **values,
        )
        MemoryScope.objects.create(
            memory=workspace_memory,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
        )
        MemoryScope.objects.create(
            memory=mixed_memory,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
        )
        MemoryScope.objects.create(
            memory=mixed_memory,
            scope=MemoryScope.SCOPE_USER,
            user=self.actor,
        )

        self.workspace_admin.delete_model(self.get_request(), workspace)

        self.assertFalse(Memory.objects.filter(pk=workspace_memory.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=mixed_memory.pk).exists())
        self.assertFalse(
            mixed_memory.scopes.filter(scope=MemoryScope.SCOPE_WORKSPACE).exists()
        )
        self.assertTrue(
            mixed_memory.scopes.filter(scope=MemoryScope.SCOPE_USER).exists()
        )

    def test_workspace_project_remains_protected_in_admin(self) -> None:
        workspace = Workspace.objects.create(name="Protected admin workspace")
        Project.objects.create(
            name="Protected project",
            slug="protected-admin-project",
            web="https://example.com/",
            workspace=workspace,
        )

        (
            _deleted_objects,
            _model_count,
            perms_needed,
            protected,
        ) = self.workspace_admin.get_deleted_objects([workspace], self.get_request())

        self.assertNotIn("Group", perms_needed)
        self.assertTrue(protected)

    def test_workspace_billing_remains_protected_in_admin(self) -> None:
        billing = create_test_billing(self.actor, invoice=False)

        (
            _deleted_objects,
            _model_count,
            perms_needed,
            protected,
        ) = self.workspace_admin.get_deleted_objects(
            [billing.workspace], self.get_request()
        )

        self.assertNotIn("Group", perms_needed)
        self.assertTrue(protected)
