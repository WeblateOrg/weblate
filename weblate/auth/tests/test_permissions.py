# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from weblate.auth.data import (
    GLOBAL_PERM_NAMES,
    PERMISSION_NAMES,
    SELECTION_ALL,
    SELECTION_ALL_PROTECTED,
    SELECTION_ALL_PUBLIC,
    SELECTION_COMPONENT_LIST,
    SELECTION_MANUAL,
)
from weblate.auth.models import Group, Permission, Role, TeamMembership, User
from weblate.auth.permissions import check_permission
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Change,
    Comment,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import create_test_billing
from weblate.utils.change_origin import acting_user_context
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.results import PermissionResult


class PermissionsTest(FixtureComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("user", "test@example.com")
        self.admin = User.objects.create_user("admin", "admin@example.com")
        self.superuser = User.objects.create_user(
            "super", "super@example.com", is_superuser=True
        )
        self.project.add_user(self.admin, "Administration")

    def test_permission_overlap(self) -> None:
        self.assertEqual(PERMISSION_NAMES & GLOBAL_PERM_NAMES, set())

    def test_admin_perm(self) -> None:
        self.assertTrue(self.superuser.has_perm("upload.authorship", self.project))
        self.assertTrue(self.admin.has_perm("upload.authorship", self.project))
        self.assertFalse(self.user.has_perm("upload.authorship", self.project))

    def test_user_perm(self) -> None:
        self.assertTrue(self.superuser.has_perm("comment.add", self.project))
        self.assertTrue(self.admin.has_perm("comment.add", self.project))
        self.assertTrue(self.user.has_perm("comment.add", self.project))

    def test_delete_comment(self) -> None:
        comment = Comment(unit=self.get_unit())
        self.assertTrue(self.superuser.has_perm("comment.delete", comment))
        self.assertTrue(self.admin.has_perm("comment.delete", comment))
        self.assertFalse(self.user.has_perm("comment.delete", comment))

    def test_delete_owned_comment(self) -> None:
        comment = Comment(unit=self.get_unit(), user=self.user)
        self.assertTrue(self.superuser.has_perm("comment.delete", comment))
        self.assertTrue(self.admin.has_perm("comment.delete", comment))
        self.assertTrue(self.user.has_perm("comment.delete", comment))

    def test_delete_not_owned_comment(self) -> None:
        comment = Comment(unit=self.get_unit(), user=self.admin)
        self.assertTrue(self.superuser.has_perm("comment.delete", comment))
        self.assertTrue(self.admin.has_perm("comment.delete", comment))
        self.assertFalse(self.user.has_perm("comment.delete", comment))

    @override_settings(AUTH_RESTRICT_ADMINS={"super": ("trans.add_project",)})
    def test_restrict_super(self) -> None:
        self.assertFalse(self.superuser.has_perm("trans.change_project"))
        self.assertFalse(self.admin.has_perm("trans.change_project"))
        self.assertFalse(self.user.has_perm("trans.change_project"))
        self.assertTrue(self.superuser.has_perm("trans.add_project"))
        self.assertFalse(self.admin.has_perm("trans.add_project"))
        self.assertFalse(self.user.has_perm("trans.add_project"))
        # Should have no effect here
        self.test_delete_comment()

    @override_settings(AUTH_RESTRICT_ADMINS={"admin": ("trans.add_project",)})
    def test_restrict_admin(self) -> None:
        self.assertTrue(self.superuser.has_perm("trans.change_project"))
        self.assertFalse(self.admin.has_perm("trans.change_project"))
        self.assertFalse(self.user.has_perm("trans.change_project"))
        self.assertTrue(self.superuser.has_perm("trans.add_project"))
        self.assertFalse(self.admin.has_perm("trans.add_project"))
        self.assertFalse(self.user.has_perm("trans.add_project"))
        # Should have no effect here
        self.test_delete_comment()

    def test_global_perms(self) -> None:
        self.assertTrue(self.superuser.has_perm("management.use"))
        self.assertFalse(self.admin.has_perm("management.use"))
        self.assertFalse(self.user.has_perm("management.use"))

    def grant_global_management_permission(
        self, *, enforced_2fa: bool = False, user: User | None = None
    ) -> None:
        target = user or self.user
        permission = Permission.objects.get(codename="management.use")

        role = Role.objects.create(name="Nearly superuser")
        role.permissions.add(permission)

        group = Group.objects.create(name="Nearly superuser", enforced_2fa=enforced_2fa)
        group.roles.add(role)

        target.groups.add(group)
        target.clear_permissions_cache()

    def test_global_perms_granted(self) -> None:
        self.grant_global_management_permission()

        self.assertTrue(self.user.has_perm("management.use"))

    def test_global_perms_granted_with_enforced_2fa(self) -> None:
        self.grant_global_management_permission(enforced_2fa=True)

        self.assertFalse(self.user.has_perm("management.use"))

        device = TOTPDevice.objects.create(user=self.user, confirmed=False)
        user = User.objects.get(pk=self.user.pk)
        self.assertFalse(user.has_perm("management.use"))

        device.confirmed = True
        device.save(update_fields=["confirmed"])
        user = User.objects.get(pk=self.user.pk)

        self.assertTrue(user.has_perm("management.use"))

    def test_global_perms_granted_with_enforced_2fa_bot(self) -> None:
        bot = User.objects.create_user(
            "management-bot", "management-bot@example.com", is_bot=True
        )
        self.grant_global_management_permission(enforced_2fa=True, user=bot)

        self.assertTrue(bot.has_perm("management.use"))

    def test_workspace_permissions_are_not_sitewide(self) -> None:
        workspace = Workspace.objects.create(name="Global workspace")
        group = Group.objects.get(name="Managers")
        self.user.groups.add(group)

        self.assertFalse(self.user.has_perm("workspace.edit", workspace))

    def test_workspace_permissions_are_not_project_scoped(self) -> None:
        workspace = Workspace.objects.create(name="Project workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.admin.clear_permissions_cache()

        self.assertFalse(self.admin.has_perm("workspace.edit", workspace))

    def test_workspace_permissions(self) -> None:
        workspace = Workspace.objects.create(name="Workspace")
        workspace.add_owner(self.user)

        self.assertTrue(self.user.has_perm("workspace.edit", workspace))
        self.assertTrue(self.user.has_perm("reports.view", workspace))

    def test_workspace_reports_permission_requires_project_2fa(self) -> None:
        workspace = Workspace.objects.create(name="Workspace with enforced 2FA")
        self.project.workspace = workspace
        self.project.enforced_2fa = True
        self.project.save(update_fields=["workspace", "enforced_2fa"])
        workspace.add_owner(self.user)
        self.user.clear_permissions_cache()

        self.assertTrue(self.superuser.has_perm("reports.view", workspace))
        self.assertTrue(self.user.has_perm("workspace.edit", workspace))
        self.assertFalse(self.user.has_perm("reports.view", workspace))

        TOTPDevice.objects.create(user=self.user)
        user = User.objects.get(pk=self.user.pk)

        self.assertTrue(user.has_perm("reports.view", workspace))

    def test_reports_role_is_assignable_to_workspace_team(self) -> None:
        role = Role.objects.create(name="Workspace report viewer")
        role.permissions.add(Permission.objects.get(codename="reports.view"))

        self.assertIn(role, Role.objects.assignable_to_workspace_team())
        self.assertNotIn(
            Role.objects.get(name="Administration"),
            Role.objects.assignable_to_workspace_team(),
        )

    def test_administration_role_is_project_scoped(self) -> None:
        self.assertFalse(
            Role.objects.get(name="Administration").permissions.filter(
                codename="workspace.edit"
            )
        )
        self.assertTrue(
            Role.objects.get(name="Workspace administration").permissions.filter(
                codename="workspace.edit"
            )
        )

    def test_project_creators_can_add_workspaces(self) -> None:
        self.user.groups.add(Group.objects.get(name="Project creators"))

        self.assertTrue(self.user.has_perm("project.add"))
        self.assertTrue(self.user.has_perm("workspace.add"))

    def test_scoped_teams_do_not_grant_global_permissions(self) -> None:
        role = Role.objects.create(name="Scoped global permission")
        role.permissions.add(Permission.objects.get(codename="user.edit"))

        sitewide_team = Group.objects.create(name="Site-wide global permission")
        project_team = Group.objects.create(
            name="Project global permission", defining_project=self.project
        )
        workspace = Workspace.objects.create(name="Global permission workspace")
        workspace_team = Group.objects.create(
            name="Workspace global permission", defining_workspace=workspace
        )
        for team in (sitewide_team, project_team, workspace_team):
            team.roles.add(role)

        sitewide_user = User.objects.create_user(
            "sitewide-global", "sitewide-global@example.com"
        )
        project_user = User.objects.create_user(
            "project-global", "project-global@example.com"
        )
        workspace_user = User.objects.create_user(
            "workspace-global", "workspace-global@example.com"
        )
        sitewide_user.groups.add(sitewide_team)
        project_user.groups.add(project_team)
        workspace_user.groups.add(workspace_team)

        self.assertTrue(sitewide_user.has_perm("user.edit"))
        self.assertFalse(project_user.has_perm("user.edit"))
        self.assertFalse(workspace_user.has_perm("user.edit"))

    def test_restricted_component(self) -> None:
        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertTrue(self.admin.has_perm("unit.edit", self.component))
        self.assertTrue(self.user.has_perm("unit.edit", self.component))

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertFalse(self.admin.has_perm("unit.edit", self.component))
        self.assertFalse(self.user.has_perm("unit.edit", self.component))

    def test_project_edit_grants_restricted_component_administration(self) -> None:
        role = Role.objects.create(name="Project settings only")
        role.permissions.add(Permission.objects.get(codename="project.edit"))
        group = Group.objects.create(name="Project settings administrators")
        group.roles.add(role)
        group.projects.add(self.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        unit = self.get_unit()
        change = Change.objects.create(
            component=self.component, action=ActionEvents.CHANGE, user=self.admin
        )
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        self.assertNotIn(self.component.pk, self.user.component_permissions)
        self.assertTrue(self.user.can_access_component(self.component))
        self.assertTrue(self.user.has_perm("component.edit", self.component))
        self.assertTrue(
            Component.objects.filter_permission_scope(self.user, "component.edit")
            .filter(pk=self.component.pk)
            .exists()
        )
        self.assertFalse(self.user.has_perm("unit.edit", unit))
        self.assertFalse(self.user.has_perm("translation.download", unit.translation))
        self.assertFalse(
            Component.objects.filter_permission_scope(self.user, "translation.download")
            .filter(pk=self.component.pk)
            .exists()
        )

        urls = (
            reverse(
                "api:component-detail",
                kwargs={
                    "project__slug": self.project.slug,
                    "slug": self.component.slug,
                },
            ),
            reverse("api:unit-detail", kwargs={"pk": unit.pk}),
            reverse("api:change-detail", kwargs={"pk": change.pk}),
        )
        outsider = User.objects.create_user(
            "restricted-outsider", "restricted-outsider@example.com"
        )
        self.assertFalse(outsider.can_access_component(self.component))
        client = APIClient()
        for user, expected_status in (
            (self.user, 200),
            (self.admin, 200),
            (outsider, 404),
        ):
            client.force_authenticate(user)
            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(client.get(url).status_code, expected_status)

        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(self.component.get_absolute_url()).status_code, 200
        )

        self.user.groups.remove(group)
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.can_access_component(self.component))
        self.assertFalse(
            Component.objects.filter_access(self.user)
            .filter(pk=self.component.pk)
            .exists()
        )
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.assertFalse(self.user.can_access_component(self.component))
        self.assertFalse(
            Component.objects.filter_access(self.user)
            .filter(pk=self.component.pk)
            .exists()
        )

    def test_project_admin_restricted_actions_require_component_grants(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        translation = self.get_unit().translation
        actions = ("unit.edit", "unit.review", "translation.download")
        role = Role.objects.create(name="Restricted translation actions")
        role.permissions.add(*Permission.objects.filter(codename__in=actions))
        group = Group.objects.create(
            name="Restricted translation editors", language_selection=SELECTION_ALL
        )
        group.roles.add(role)
        group.projects.add(self.project)
        self.admin.groups.add(group)
        self.admin.clear_permissions_cache()

        self.assertTrue(self.admin.can_access_component(self.component))
        self.assertTrue(self.admin.has_perm("component.edit", self.component))
        for component_grant in (False, True):
            if component_grant:
                group.components.add(self.component)
                self.admin.clear_permissions_cache()
            for permission in actions:
                with self.subTest(
                    component_grant=component_grant, permission=permission
                ):
                    self.assertTrue(
                        check_permission(self.admin, permission, self.project)
                    )
                    self.assertEqual(
                        bool(check_permission(self.admin, permission, translation)),
                        component_grant,
                    )
                    self.assertEqual(
                        Translation.objects.filter_permission_scope(
                            self.admin, permission
                        )
                        .filter(pk=translation.pk)
                        .exists(),
                        component_grant,
                    )

    def test_async_restricted_access_prepares_profile(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        async def check_access(user: User) -> None:
            await user.aprepare_permissions()
            self.assertTrue(user.needs_component_restrictions_filter)
            self.assertTrue(
                await Component.objects.filter_access(user)
                .filter(pk=self.component.pk)
                .aexists()
            )

        for load_profile in (False, True):
            with self.subTest(load_profile=load_profile):
                users = User.objects.all()
                if load_profile:
                    users = users.select_related("profile")
                user = users.get(pk=self.admin.pk)
                # ruff: ignore[private-member-access]
                self.assertEqual("profile" in user._state.fields_cache, load_profile)
                async_to_sync(check_access)(user)

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_billing_component_permissions(self) -> None:
        self.assertTrue(
            self.superuser.has_perm("billing:component.permissions", Component())
        )
        self.assertTrue(self.admin.has_perm("component.edit", self.component))
        self.assertNotIn(self.component.pk, self.admin.component_permissions)
        self.assertTrue(
            self.admin.has_perm("billing:component.permissions", self.component)
        )
        self.assertNotIn(self.component.pk, self.admin.component_permissions)
        self.component.restricted = True
        self.assertTrue(self.admin.can_access_component(self.component))
        self.component.restricted = False

        self.assertTrue(
            self.admin.has_perm(
                "billing:component.permissions", Component(project=self.project)
            )
        )
        self.assert_denied_reason(
            self.user.has_perm("billing:component.permissions", self.component),
            "You need explicit access to this component before enabling restricted access; otherwise, you would lock yourself out.",
        )

        role = Role.objects.create(name="Restricted component editor")
        role.permissions.add(Permission.objects.get(codename="component.edit"))
        group = Group.objects.create(name="Restricted component editors")
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        self.assertTrue(
            self.user.has_perm("billing:component.permissions", self.component)
        )
        self.assert_denied_reason(
            self.user.has_perm("billing:component.permissions", Component()),
            "Create the component and grant yourself explicit access before enabling restricted access.",
        )

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    @override_settings(OFFER_HOSTING=True)
    def test_billing_component_permissions_on_hosted(self) -> None:
        role = Role.objects.create(name="Hosted restricted component editor")
        role.permissions.add(Permission.objects.get(codename="component.edit"))
        group = Group.objects.create(name="Hosted restricted component editors")
        group.roles.add(role)
        group.components.add(self.component)
        self.admin.groups.add(group)
        self.admin.clear_permissions_cache()

        self.assert_denied_reason(
            self.admin.has_perm("billing:component.permissions", self.component),
            "The billing plan does not allow private access control.",
        )

        project = Project.objects.get(pk=self.project.pk)
        billing = create_test_billing(self.admin)
        billing.add_project(project)
        component = Component.objects.select_related("project").get(
            pk=self.component.pk
        )
        self.assertTrue(self.admin.has_perm("billing:component.permissions", component))

        billing.plan.change_access_control = False
        billing.plan.save(update_fields=["change_access_control"])
        project.access_control = Project.ACCESS_PROTECTED
        self.enterContext(acting_user_context(self.admin))
        project.save(update_fields=["access_control"])
        component = Component.objects.select_related("project").get(
            pk=self.component.pk
        )
        self.assert_denied_reason(
            self.admin.has_perm("billing:component.permissions", component),
            "The billing plan does not allow private access control.",
        )

        component.restricted = True
        self.enterContext(acting_user_context(self.admin))
        component.save(update_fields=["restricted"])
        self.assertTrue(self.admin.has_perm("billing:component.permissions", component))

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_billing_component_permissions_reject_language_limited_access(
        self,
    ) -> None:
        role = Role.objects.create(name="Language limited component editor")
        role.permissions.add(Permission.objects.get(codename="component.edit"))
        group = Group.objects.create(name="Language limited component editors")
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        membership = TeamMembership.objects.get(user=self.user, group=group)
        membership.limit_languages.add(self.component.source_language)
        self.user.clear_permissions_cache()

        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.assert_denied_reason(
            self.user.has_perm("billing:component.permissions", self.component),
            "You need explicit access to this component before enabling restricted access; otherwise, you would lock yourself out.",
        )

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.assertFalse(self.user.has_perm("component.edit", self.component))

    def assert_denied_reason(
        self, result: bool | PermissionResult, reason: str
    ) -> None:
        self.assertFalse(result)
        self.assertEqual(getattr(result, "reason", ""), reason)

    def test_glossary_permission_denial_reasons(self) -> None:
        self.component.create_glossary()
        glossary = Component.objects.get(project=self.project, is_glossary=True)
        glossary.manage_units = True
        glossary.save(update_fields=["manage_units"])
        Role.objects.get(name="Power user").permissions.remove(
            *Permission.objects.filter(
                codename__in={
                    "glossary.add",
                    "glossary.delete",
                    "glossary.edit",
                    "glossary.upload",
                }
            )
        )
        self.user.clear_permissions_cache()

        source_translation = glossary.source_translation
        unit = source_translation.add_unit(
            None, "", source="glossary-term", author=self.admin
        )
        if unit is None:
            msg = "Expected glossary unit to be created"
            raise AssertionError(msg)
        upload_translation = glossary.translation_set.exclude(
            language=glossary.source_language
        ).first()
        if upload_translation is None:
            msg = "Expected glossary translation to be created"
            raise AssertionError(msg)

        self.assert_denied_reason(
            self.user.has_perm("unit.edit", upload_translation),
            "You do not have permission to edit glossary entries.",
        )
        self.assert_denied_reason(
            self.user.has_perm("meta:unit.flag", upload_translation),
            "You do not have permission to edit glossary entries.",
        )
        self.assert_denied_reason(
            self.user.has_perm("unit.add", source_translation),
            "You do not have permission to add glossary entries.",
        )
        self.assert_denied_reason(
            self.user.has_perm("unit.delete", unit),
            "You do not have permission to delete glossary entries.",
        )
        self.assert_denied_reason(
            self.user.has_perm("upload.perform", upload_translation),
            "You do not have permission to upload glossary entries.",
        )

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_permission_billing(self) -> None:
        # Permissions should apply without billing
        with modify_settings(INSTALLED_APPS={"remove": "weblate.billing"}):
            self.assertTrue(
                self.superuser.has_perm("billing:project.permissions", self.project)
            )
            self.assertTrue(
                self.admin.has_perm("billing:project.permissions", self.project)
            )
            self.assertFalse(
                self.user.has_perm("billing:project.permissions", self.project)
            )

        # With billing enabled and no plan it should be disabled
        self.assertTrue(
            self.superuser.has_perm("billing:project.permissions", self.project)
        )
        self.assertFalse(
            self.admin.has_perm("billing:project.permissions", self.project)
        )
        self.assertFalse(
            self.user.has_perm("billing:project.permissions", self.project)
        )

        project = Project.objects.get(pk=self.project.pk)
        billing = create_test_billing(self.admin)
        billing.add_project(project)

        # The default plan allows
        self.assertTrue(self.superuser.has_perm("billing:project.permissions", project))
        self.assertTrue(self.admin.has_perm("billing:project.permissions", project))
        self.assertFalse(self.user.has_perm("billing:project.permissions", project))

        billing.plan.change_access_control = False
        billing.plan.save()
        project = Project.objects.get(pk=self.project.pk)

        # It should be restricted now
        self.assertTrue(self.superuser.has_perm("billing:project.permissions", project))
        self.assertFalse(self.admin.has_perm("billing:project.permissions", project))
        self.assertFalse(self.user.has_perm("billing:project.permissions", project))

    def test_user_block(self) -> None:
        self.assertTrue(self.user.has_perm("unit.edit", self.component))

        # Block user
        self.user.clear_permissions_cache()
        self.user.userblock_set.create(project=self.project)
        self.assertFalse(self.user.has_perm("unit.edit", self.component))
        self.user.userblock_set.all().delete()

        # Block user with past expiry
        self.user.clear_permissions_cache()
        self.user.userblock_set.create(
            project=self.project, expiry=timezone.now() - timedelta(days=1)
        )
        self.assertTrue(self.user.has_perm("unit.edit", self.component))
        self.user.userblock_set.all().delete()

        # Block user with future expiry
        self.user.clear_permissions_cache()
        self.user.userblock_set.create(
            project=self.project, expiry=timezone.now() + timedelta(days=1)
        )
        self.assertFalse(self.user.has_perm("unit.edit", self.component))
        self.user.userblock_set.all().delete()

    def test_projects_with_perm_blocked(self) -> None:
        self.project.add_user(self.user, "Administration")
        other_project = Project.objects.create(slug="other", name="Other")
        other_project.add_user(self.user, "Administration")

        for expiry, blocked in (
            (None, True),
            (timezone.now() + timedelta(days=1), True),
            (timezone.now() - timedelta(days=1), False),
        ):
            with self.subTest(expiry=expiry):
                block = self.user.userblock_set.create(
                    project=self.project, expiry=expiry
                )
                self.user.clear_permissions_cache()
                for explicit in (False, True):
                    projects = self.user.projects_with_perm(
                        "project.edit", explicit=explicit
                    )
                    self.assertEqual(self.project in projects, not blocked)
                    self.assertIn(other_project, projects)
                self.assertEqual(
                    self.project in self.user.managed_projects, not blocked
                )
                self.assertEqual(self.project in self.user.owned_projects, not blocked)
                self.assertEqual(
                    bool(self.user.has_perm("project.edit", self.project)), not blocked
                )
                block.delete()

        self.user.clear_permissions_cache()
        self.assertIn(self.project, self.user.managed_projects)

    def test_projects_with_perm_blocked_sitewide(self) -> None:
        role = Role.objects.create(name="Project manager")
        role.permissions.add(Permission.objects.get(codename="project.edit"))
        group = Group.objects.create(name="Project managers")
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.userblock_set.create(project=self.project)
        other_project = Project.objects.create(slug="other", name="Other")

        for selection, access in (
            (SELECTION_ALL_PUBLIC, Project.ACCESS_PUBLIC),
            (SELECTION_ALL_PROTECTED, Project.ACCESS_PROTECTED),
            (SELECTION_ALL, Project.ACCESS_PRIVATE),
        ):
            with self.subTest(selection=selection):
                group.project_selection = selection
                group.save()
                Project.objects.filter(
                    pk__in=[self.project.pk, other_project.pk]
                ).update(access_control=access)
                self.user.clear_permissions_cache()
                self.assertNotIn(self.project, self.user.managed_projects)
                self.assertIn(other_project, self.user.managed_projects)
                self.assertFalse(self.user.owned_projects.exists())

    def test_projects_with_perm_blocked_superuser(self) -> None:
        self.project.add_user(self.superuser, "Administration")
        self.superuser.userblock_set.create(project=self.project)
        self.superuser.clear_permissions_cache()
        self.assertIn(self.project, self.superuser.managed_projects)
        self.assertIn(self.project, self.superuser.owned_projects)
        self.assertTrue(self.superuser.has_perm("project.edit", self.project))

    def test_projects_with_perm(self) -> None:
        group = Group.objects.get(name="Managers")

        # No membership
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

        # Admin group
        self.project.add_user(self.user)
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )

        # Superuser and admin group
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )

        # Superuser only
        self.project.remove_user(self.user)
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

        # Superuser in sitewide group
        group.user_set.add(self.user)
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

        # User in sitewide group
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

        # Public projects with membership
        group.project_selection = SELECTION_ALL_PUBLIC
        group.save()
        self.user.clear_permissions_cache()
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

        # Protected projects without membership
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.save()
        self.user.clear_permissions_cache()
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

        # Protected projects with membership
        group.project_selection = SELECTION_ALL_PROTECTED
        group.save()
        self.user.clear_permissions_cache()
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit").values_list(
                    "slug", flat=True
                )
            ),
            [self.project.slug],
        )
        self.assertEqual(
            list(
                self.user.projects_with_perm("project.edit", explicit=True).values_list(
                    "slug", flat=True
                )
            ),
            [],
        )

    def test_projects_with_perm_component_scope(self) -> None:
        administration = Role.objects.get(name="Administration")

        for scope in ("component", "component-list"):
            with self.subTest(scope=scope):
                user = User.objects.create_user(
                    f"{scope}-user", f"{scope}-user@example.com"
                )
                group = Group.objects.create(
                    name=f"{scope} administrators",
                    project_selection=(
                        SELECTION_COMPONENT_LIST
                        if scope == "component-list"
                        else SELECTION_MANUAL
                    ),
                )
                group.roles.add(administration)
                if scope == "component-list":
                    component_list = ComponentList.objects.create(
                        name="Permission scope", slug="permission-scope"
                    )
                    component_list.components.add(self.component)
                    group.componentlists.add(component_list)
                    group.save()
                else:
                    group.projects.add(self.project)
                    group.components.add(self.component)
                user.groups.add(group)
                user.clear_permissions_cache()

                self.assertTrue(user.can_access_project(self.project))
                self.assertFalse(user.has_perm("project.edit", self.project))
                self.assertFalse(
                    user.projects_with_perm("project.edit")
                    .filter(pk=self.project.pk)
                    .exists()
                )
                self.assertFalse(
                    user.projects_with_perm("project.edit", explicit=True)
                    .filter(pk=self.project.pk)
                    .exists()
                )

                unrestricted = Group.objects.create(
                    name=f"{scope} unrestricted administrators"
                )
                unrestricted.roles.add(administration)
                unrestricted.projects.add(self.project)
                user.groups.add(unrestricted)
                user.clear_permissions_cache()

                self.assertTrue(user.has_perm("project.edit", self.project))
                self.assertTrue(
                    user.projects_with_perm("project.edit")
                    .filter(pk=self.project.pk)
                    .exists()
                )
                self.assertTrue(
                    user.projects_with_perm("project.edit", explicit=True)
                    .filter(pk=self.project.pk)
                    .exists()
                )

    def test_meta_team_edit_perm(self) -> None:
        self.assertTrue(self.admin.has_perm("meta:team.edit", self.project))
        self.assertFalse(self.admin.has_perm("meta:team.edit"))
