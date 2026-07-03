# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.urls import reverse

from weblate.auth.data import SELECTION_ALL
from weblate.auth.forms import ProjectTeamForm, WorkspaceTeamForm
from weblate.auth.models import Group, Permission, Role, TeamMembership, User
from weblate.lang.models import Language
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.workspaces.models import Workspace


class TeamsTest(FixtureTestCase):
    def make_superuser(self, superuser: bool = True) -> None:
        self.user.is_superuser = superuser
        self.user.save()

    def test_sitewide(self) -> None:
        group = Group.objects.create(name="Test group")
        edit_payload = {
            "name": "Other",
            "language_selection": "1",
            "project_selection": "1",
            "autogroup_set-TOTAL_FORMS": "0",
            "autogroup_set-INITIAL_FORMS": "0",
        }
        response = self.client.get(group.get_absolute_url())
        self.assertEqual(response.status_code, 403)

        # Edit not allowed
        response = self.client.post(group.get_absolute_url(), edit_payload)
        group.refresh_from_db()
        self.assertEqual(group.name, "Test group")

        self.make_superuser()
        response = self.client.get(group.get_absolute_url())
        self.assertContains(response, "id_autogroup_set-TOTAL_FORMS")
        self.assertContains(
            response,
            "This is checked for every new user on the site, regardless of which project they use.",
        )

        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertRedirects(response, group.get_absolute_url())
        group.refresh_from_db()
        self.assertEqual(group.name, "Other")

    def test_project(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)

        edit_payload = {
            "name": "Other",
            "language_selection": "1",
            "autogroup_set-TOTAL_FORMS": "0",
            "autogroup_set-INITIAL_FORMS": "0",
        }
        response = self.client.get(group.get_absolute_url())
        self.assertEqual(response.status_code, 403)

        # Edit not allowed
        response = self.client.post(group.get_absolute_url(), edit_payload)
        group.refresh_from_db()
        self.assertEqual(group.name, "Test group")

        self.make_superuser()
        response = self.client.get(group.get_absolute_url())
        self.assertContains(response, "id_autogroup_set-TOTAL_FORMS")

        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertRedirects(response, group.get_absolute_url())
        group.refresh_from_db()
        self.assertEqual(group.name, "Other")

    def test_project_team_form_roles(self) -> None:
        global_role = Role.objects.create(name="Global project")
        global_role.permissions.add(
            Permission.objects.get(codename="project.add"),
            Permission.objects.get(codename="translation.add"),
        )
        workspace_role = Role.objects.create(name="Workspace project")
        workspace_role.permissions.add(
            Permission.objects.get(codename="workspace.edit"),
            Permission.objects.get(codename="translation.add"),
        )

        form = ProjectTeamForm(self.project)
        roles = set(form.fields["roles"].queryset)

        self.assertIn(Role.objects.get(name="Administration"), roles)
        self.assertNotIn(global_role, roles)
        self.assertNotIn(workspace_role, roles)
        self.assertNotIn(Role.objects.get(name="Workspace administration"), roles)

    def test_workspace_team_form_roles(self) -> None:
        workspace = Workspace.objects.create(name="Workspace")
        workspace_role = Role.objects.create(name="Custom workspace")
        workspace_role.permissions.add(
            Permission.objects.get(codename="workspace.edit")
        )
        global_role = Role.objects.create(name="Global workspace")
        global_role.permissions.add(
            Permission.objects.get(codename="workspace.edit"),
            Permission.objects.get(codename="project.add"),
        )
        project_role = Role.objects.create(name="Project")
        project_role.permissions.add(Permission.objects.get(codename="project.edit"))

        form = WorkspaceTeamForm(workspace)
        roles = set(form.fields["roles"].queryset)

        self.assertIn(workspace_role, roles)
        self.assertNotIn(global_role, roles)
        self.assertNotIn(project_role, roles)

    def test_workspace_team_form_uses_all_languages(self) -> None:
        workspace = Workspace.objects.create(name="Workspace")
        group = Group.objects.create(name="Test group", defining_workspace=workspace)

        form = WorkspaceTeamForm(
            workspace,
            {
                "name": group.name,
                "roles": [],
                "autogroup_set-TOTAL_FORMS": "0",
                "autogroup_set-INITIAL_FORMS": "0",
            },
            instance=group,
        )

        self.assertTrue(form.is_valid())
        form.save()
        group.refresh_from_db()
        self.assertEqual(group.language_selection, SELECTION_ALL)

    def test_workspace_internal_team_delete(self) -> None:
        workspace = Workspace.objects.create(name="Workspace")
        workspace.add_owner(self.user)
        group = workspace.get_owners_group()

        response = self.client.post(group.get_absolute_url(), {"delete": "1"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("workspace-access", kwargs={"pk": workspace.pk}),
        )
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())

    def test_add_users(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)

        # Non-privileged
        self.client.post(
            group.get_absolute_url(), {"add_user": "1", "user": self.user.username}
        )
        self.assertEqual(group.user_set.count(), 0)
        self.assertEqual(group.admins.count(), 0)

        # Superuser
        self.make_superuser()
        self.client.post(
            group.get_absolute_url(), {"add_user": "1", "user": "x-invalid"}
        )
        self.assertEqual(group.user_set.count(), 0)
        self.assertEqual(group.admins.count(), 0)
        self.client.post(
            group.get_absolute_url(), {"add_user": "1", "user": self.user.username}
        )
        self.assertEqual(group.user_set.count(), 1)
        self.assertEqual(group.admins.count(), 0)
        self.assertFalse(
            TeamMembership.objects.get(
                user=self.user, group=group
            ).limit_languages.exists()
        )

        self.client.post(
            group.get_absolute_url(),
            {
                "add_user": "add",
                "user": self.user.username,
                "limit_languages": ["cs"],
            },
        )
        self.assertEqual(
            list(
                TeamMembership.objects.get(
                    user=self.user, group=group
                ).limit_languages.values_list("code", flat=True)
            ),
            ["cs"],
        )

        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.user.username, "make_admin": "1"},
        )
        self.assertEqual(group.user_set.count(), 1)
        self.assertEqual(group.admins.count(), 1)
        self.assertEqual(
            list(
                TeamMembership.objects.get(
                    user=self.user, group=group
                ).limit_languages.values_list("code", flat=True)
            ),
            ["cs"],
        )

        self.client.post(
            group.get_absolute_url(),
            {
                "add_user": "add",
                "user": self.user.username,
            },
        )
        self.assertFalse(
            TeamMembership.objects.get(
                user=self.user, group=group
            ).limit_languages.exists()
        )
        group.admins.add(self.user)

        # Team admin
        self.make_superuser(False)
        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 1)

        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username, "make_admin": "1"},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 2)

        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 1)

    def test_user_list_orders_limit_languages(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)
        membership = TeamMembership.objects.create(user=self.user, group=group)
        membership.limit_languages.add(Language.objects.get(code="de"))
        membership.limit_languages.add(Language.objects.get(code="cs"))
        self.make_superuser()

        response = self.client.get(group.get_absolute_url())

        listed_user = next(iter(response.context["users"]))
        with self.assertNumQueries(0):
            limit_languages = list(listed_user.team_membership.limit_languages.all())
        self.assertEqual(
            [language.code for language in limit_languages],
            ["cs", "de"],
        )

    def test_add_special_users_denied(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)
        self.user.groups.add(group)
        group.admins.add(self.user)
        inactive = User.objects.create_user(
            "inactive-user", "inactive-user@example.org", "testpassword"
        )
        inactive.is_active = False
        inactive.save()
        bot = User.objects.create(
            username="bot-user",
            full_name="Bot user",
            email="bot-user@example.org",
            is_bot=True,
        )
        users = [
            User.objects.get(username=settings.ANONYMOUS_USER_NAME),
            inactive,
            bot,
        ]

        for user in users:
            for payload in (
                {"add_user": "1", "user": user.username},
                {"add_user": "1", "user": user.username, "make_admin": "1"},
            ):
                self.client.post(group.get_absolute_url(), payload)
                self.assertFalse(group.user_set.filter(pk=user.pk).exists())
                self.assertFalse(group.admins.filter(pk=user.pk).exists())

    def test_anonymous_team_admin_denied(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)
        anonymous = User.objects.get(username=settings.ANONYMOUS_USER_NAME)
        anonymous.groups.add(group)
        group.admins.add(anonymous)
        self.client.logout()

        response = self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(group.user_set.filter(pk=self.anotheruser.pk).exists())

    def test_admin_access(self) -> None:
        group = Group.objects.create(name="Test group", defining_project=self.project)
        self.user.groups.add(group)
        group.admins.add(self.user)

        response = self.client.get(group.get_absolute_url())

        self.assertNotContains(response, "Enforced two-factor authentication")
        self.assertContains(response, "Add a user")

        # Add user should work
        self.client.post(
            group.get_absolute_url(),
            {"add_user": "1", "user": self.anotheruser.username},
        )
        self.assertEqual(group.user_set.count(), 2)
        self.assertEqual(group.admins.count(), 1)

        # Edit should not work
        edit_payload = {
            "name": "Other",
            "language_selection": "1",
            "autogroup_set-TOTAL_FORMS": "0",
            "autogroup_set-INITIAL_FORMS": "0",
        }

        # Edit not allowed
        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertEqual(response.status_code, 403)

        # Verify no changes were done
        group.refresh_from_db()
        self.assertEqual(group.name, "Test group")
