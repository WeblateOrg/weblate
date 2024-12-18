# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from django.test.utils import modify_settings, override_settings
from django.utils import timezone

from weblate.auth.data import (
    GLOBAL_PERM_NAMES,
    PERMISSION_NAMES,
    SELECTION_ALL_PROTECTED,
    SELECTION_ALL_PUBLIC,
)
from weblate.auth.models import Group, Permission, Role, User
from weblate.trans.models import Comment, Project
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import create_test_billing


class PermissionsTest(FixtureTestCase):
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

    def test_global_perms_granted(self) -> None:
        permission = Permission.objects.get(codename="management.use")

        role = Role.objects.create(name="Nearly superuser")
        role.permissions.add(permission)

        group = Group.objects.create(name="Nearly superuser")
        group.roles.add(role)

        self.user.groups.add(group)

        self.assertTrue(self.user.has_perm("management.use"))

    def test_restricted_component(self) -> None:
        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertTrue(self.admin.has_perm("unit.edit", self.component))
        self.assertTrue(self.user.has_perm("unit.edit", self.component))

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertFalse(self.admin.has_perm("unit.edit", self.component))
        self.assertFalse(self.user.has_perm("unit.edit", self.component))

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
        billing.projects.add(project)

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
        self.user.clear_cache()
        self.user.userblock_set.create(project=self.project)
        self.assertFalse(self.user.has_perm("unit.edit", self.component))
        self.user.userblock_set.all().delete()

        # Block user with past expiry
        self.user.clear_cache()
        self.user.userblock_set.create(
            project=self.project, expiry=timezone.now() - timedelta(days=1)
        )
        self.assertTrue(self.user.has_perm("unit.edit", self.component))
        self.user.userblock_set.all().delete()

        # Block user with future expiry
        self.user.clear_cache()
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
        self.user.clear_cache()
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
        self.user.clear_cache()
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
        self.user.clear_cache()
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
