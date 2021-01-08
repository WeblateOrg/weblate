#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.test.utils import modify_settings, override_settings

from weblate.auth.models import Group, Permission, Role, User
from weblate.trans.models import Comment, Project
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import create_test_billing


class PermissionsTest(FixtureTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("user", "test@example.com")
        self.admin = User.objects.create_user("admin", "admin@example.com")
        self.superuser = User.objects.create_user(
            "super", "super@example.com", is_superuser=True
        )
        self.project.add_user(self.admin, "@Administration")

    def test_admin_perm(self):
        self.assertTrue(self.superuser.has_perm("upload.authorship", self.project))
        self.assertTrue(self.admin.has_perm("upload.authorship", self.project))
        self.assertFalse(self.user.has_perm("upload.authorship", self.project))

    def test_user_perm(self):
        self.assertTrue(self.superuser.has_perm("comment.add", self.project))
        self.assertTrue(self.admin.has_perm("comment.add", self.project))
        self.assertTrue(self.user.has_perm("comment.add", self.project))

    def test_delete_comment(self):
        comment = Comment(unit=self.get_unit())
        self.assertTrue(self.superuser.has_perm("comment.delete", comment))
        self.assertTrue(self.admin.has_perm("comment.delete", comment))
        self.assertFalse(self.user.has_perm("comment.delete", comment))

    def test_delete_owned_comment(self):
        comment = Comment(unit=self.get_unit(), user=self.user)
        self.assertTrue(self.superuser.has_perm("comment.delete", comment))
        self.assertTrue(self.admin.has_perm("comment.delete", comment))
        self.assertTrue(self.user.has_perm("comment.delete", comment))

    def test_delete_not_owned_comment(self):
        comment = Comment(unit=self.get_unit(), user=self.admin)
        self.assertTrue(self.superuser.has_perm("comment.delete", comment))
        self.assertTrue(self.admin.has_perm("comment.delete", comment))
        self.assertFalse(self.user.has_perm("comment.delete", comment))

    @override_settings(AUTH_RESTRICT_ADMINS={"super": ("trans.add_project",)})
    def test_restrict_super(self):
        self.assertFalse(self.superuser.has_perm("trans.change_project"))
        self.assertFalse(self.admin.has_perm("trans.change_project"))
        self.assertFalse(self.user.has_perm("trans.change_project"))
        self.assertTrue(self.superuser.has_perm("trans.add_project"))
        self.assertFalse(self.admin.has_perm("trans.add_project"))
        self.assertFalse(self.user.has_perm("trans.add_project"))
        # Should have no effect here
        self.test_delete_comment()

    @override_settings(AUTH_RESTRICT_ADMINS={"admin": ("trans.add_project",)})
    def test_restrict_admin(self):
        self.assertTrue(self.superuser.has_perm("trans.change_project"))
        self.assertFalse(self.admin.has_perm("trans.change_project"))
        self.assertFalse(self.user.has_perm("trans.change_project"))
        self.assertTrue(self.superuser.has_perm("trans.add_project"))
        self.assertFalse(self.admin.has_perm("trans.add_project"))
        self.assertFalse(self.user.has_perm("trans.add_project"))
        # Should have no effect here
        self.test_delete_comment()

    def test_global_perms(self):
        self.assertTrue(self.superuser.has_perm("management.use"))
        self.assertFalse(self.admin.has_perm("management.use"))
        self.assertFalse(self.user.has_perm("management.use"))

    def test_global_perms_granted(self):
        permission = Permission.objects.get(codename="management.use")

        role = Role.objects.create(name="Nearly superuser")
        role.permissions.add(permission)

        group = Group.objects.create(name="Nearly superuser")
        group.roles.add(role)

        self.user.groups.add(group)

        self.assertTrue(self.user.has_perm("management.use"))

    def test_restricted_component(self):
        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertTrue(self.admin.has_perm("unit.edit", self.component))
        self.assertTrue(self.user.has_perm("unit.edit", self.component))

        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        self.assertTrue(self.superuser.has_perm("unit.edit", self.component))
        self.assertFalse(self.admin.has_perm("unit.edit", self.component))
        self.assertFalse(self.user.has_perm("unit.edit", self.component))

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_permission_billing(self):
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
        self.assertFalse(
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
        self.assertFalse(
            self.superuser.has_perm("billing:project.permissions", project)
        )
        self.assertFalse(self.admin.has_perm("billing:project.permissions", project))
        self.assertFalse(self.user.has_perm("billing:project.permissions", project))
