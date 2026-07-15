# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from weblate.auth.data import (
    GLOBAL_PERM_NAMES,
    PERMISSION_NAMES,
    SELECTION_ALL_PROTECTED,
    SELECTION_ALL_PUBLIC,
)
from weblate.auth.models import Group, Permission, Role, TeamMembership, User
from weblate.trans.models import Comment, Component, Project
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.trans.tests.utils import create_test_billing
from weblate.workspaces.models import Workspace


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

        TOTPDevice.objects.create(user=self.user)
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

    def test_restricted_component(self) -> None:
        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertTrue(self.admin.has_perm("unit.edit", self.component))
        self.assertTrue(self.user.has_perm("unit.edit", self.component))

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertFalse(self.admin.has_perm("unit.edit", self.component))
        self.assertFalse(self.user.has_perm("unit.edit", self.component))

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_billing_component_permissions(self) -> None:
        self.assertTrue(
            self.superuser.has_perm("billing:component.permissions", Component())
        )
        self.assertTrue(self.admin.has_perm("component.edit", self.component))
        self.assertNotIn(self.component.pk, self.admin.component_permissions)
        self.assert_denied_reason(
            self.admin.has_perm("billing:component.permissions", self.component),
            "You need explicit access to this component before enabling restricted access; otherwise, you would lock yourself out.",
        )
        self.assertNotIn(self.component.pk, self.admin.component_permissions)
        self.component.restricted = True
        self.assertFalse(self.admin.can_access_component(self.component))
        self.component.restricted = False

        role = Role.objects.create(name="Restricted component editor")
        role.permissions.add(Permission.objects.get(codename="component.edit"))
        group = Group.objects.create(name="Restricted component editors")
        group.roles.add(role)
        group.components.add(self.component)
        self.admin.groups.add(group)
        self.admin.clear_permissions_cache()

        self.assertTrue(
            self.admin.has_perm("billing:component.permissions", self.component)
        )
        self.assert_denied_reason(
            self.admin.has_perm("billing:component.permissions", Component()),
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
        project.save(update_fields=["access_control"])
        component = Component.objects.select_related("project").get(
            pk=self.component.pk
        )
        self.assert_denied_reason(
            self.admin.has_perm("billing:component.permissions", component),
            "The billing plan does not allow private access control.",
        )

        component.restricted = True
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
        self.admin.groups.add(group)
        membership = TeamMembership.objects.get(user=self.admin, group=group)
        membership.limit_languages.add(self.component.source_language)
        self.admin.clear_permissions_cache()

        self.assertTrue(self.admin.has_perm("component.edit", self.component))
        self.assert_denied_reason(
            self.admin.has_perm("billing:component.permissions", self.component),
            "You need explicit access to this component before enabling restricted access; otherwise, you would lock yourself out.",
        )

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.assertFalse(self.admin.has_perm("component.edit", self.component))

    def assert_denied_reason(self, result, reason: str) -> None:
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

    def test_meta_team_edit_perm(self) -> None:
        self.assertTrue(self.admin.has_perm("meta:team.edit", self.project))
        self.assertFalse(self.admin.has_perm("meta:team.edit"))
