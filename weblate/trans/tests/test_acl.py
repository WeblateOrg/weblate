# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

"""Test for ACL management."""

from django.conf import settings
from django.urls import reverse
from weblate.auth.models import User, Group

from weblate.trans.models import Project
from weblate.trans.tests.test_views import FixtureTestCase


class ACLTest(FixtureTestCase):
    def setUp(self):
        super(ACLTest, self).setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = reverse('manage-access', kwargs=self.kw_project)
        self.translate_url = reverse('translate', kwargs=self.kw_translation)
        self.second_user = User.objects.create_user(
            'seconduser',
            'noreply@example.org',
            'testpassword'
        )
        self.admin_group = self.project.group_set.get(
            name__endswith='@Administration'
        )

    def add_acl(self):
        """Add user to ACL."""
        self.project.add_user(self.user, '@Translate')

    def test_acl_denied(self):
        """No access to the project without ACL.
        """
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)

    def test_acl_disable(self):
        """Test disabling ACL.
        """
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.save()
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.translate_url)
        self.assertContains(response, 'type="submit" name="save"')

    def test_acl_protected(self):
        """Test ACL protected project.
        """
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.save()
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.translate_url)
        self.assertContains(
            response, 'Insufficient privileges for saving translations.'
        )

    def test_acl(self):
        """Regular user should not have access to user management.
        """
        self.add_acl()
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)

    def test_edit_acl(self):
        """Manager should have access to user management.
        """
        self.add_acl()
        self.make_manager()
        response = self.client.get(self.access_url)
        self.assertContains(response, 'Users')

    def test_edit_acl_owner(self):
        """Owner should have access to user management.
        """
        self.add_acl()
        self.project.add_user(self.user, '@Administration')
        response = self.client.get(self.access_url)
        self.assertContains(response, 'Users')

    def add_user(self):
        self.add_acl()
        self.project.add_user(self.user, '@Administration')

        # Add user
        response = self.client.post(
            reverse('add-user', kwargs=self.kw_project),
            {'user': self.second_user.username}
        )
        self.assertRedirects(response, self.access_url)

        # Ensure user is now listed
        response = self.client.get(self.access_url)
        self.assertContains(response, self.second_user.username)
        self.assertContains(response, self.second_user.email)

    def remove_user(self):
        # Remove user
        response = self.client.post(
            reverse('delete-user', kwargs=self.kw_project),
            {'user': self.second_user.username}
        )
        self.assertRedirects(response, self.access_url)

        # Ensure user is now not listed
        response = self.client.get(self.access_url)
        self.assertNotContains(response, self.second_user.username)
        self.assertNotContains(response, self.second_user.email)

    def test_add_acl(self):
        """Adding and removing user from the ACL project.
        """
        self.add_user()
        self.remove_user()

    def test_add_owner(self):
        """Adding and removing owner from the ACL project.
        """
        self.add_user()
        self.client.post(
            reverse('set-groups', kwargs=self.kw_project),
            {
                'user': self.second_user.username,
                'group': self.admin_group.pk,
                'action': 'add',
            }
        )
        self.assertTrue(
            User.objects.all_admins(self.project).filter(
                username=self.second_user.username
            ).exists()
        )
        self.client.post(
            reverse('set-groups', kwargs=self.kw_project),
            {
                'user': self.second_user.username,
                'group': self.admin_group.pk,
                'action': 'remove',
            }
        )
        self.assertFalse(
            User.objects.all_admins(self.project).filter(
                username=self.second_user.username
            ).exists()
        )
        self.remove_user()

    def test_delete_owner(self):
        """Adding and deleting owner from the ACL project.
        """
        self.add_user()
        self.client.post(
            reverse('set-groups', kwargs=self.kw_project),
            {
                'user': self.second_user.username,
                'group': self.admin_group.pk,
                'action': 'add',
            }
        )
        self.remove_user()
        self.assertFalse(
            User.objects.all_admins(self.project).filter(
                username=self.second_user.username
            ).exists()
        )

    def test_denied_owner_delete(self):
        """Test that deleting last owner does not work."""
        self.project.add_user(self.user, '@Administration')
        self.client.post(
            reverse('set-groups', kwargs=self.kw_project),
            {
                'user': self.second_user.username,
                'group': self.admin_group.pk,
                'action': 'remove',
            }
        )
        self.assertTrue(
            User.objects.all_admins(self.project).filter(
                username=self.user.username
            ).exists()
        )
        self.client.post(
            reverse('set-groups', kwargs=self.kw_project),
            {
                'user': self.user.username,
                'group': self.admin_group.pk,
                'action': 'remove',
            }
        )
        self.assertTrue(
            User.objects.all_admins(self.project).filter(
                username=self.user.username
            ).exists()
        )

    def test_nonexisting_user(self):
        """Test adding non existing user."""
        self.project.add_user(self.user, '@Administration')
        response = self.client.post(
            reverse('add-user', kwargs=self.kw_project),
            {'user': 'nonexisting'},
            follow=True
        )
        self.assertContains(response, 'No matching user found.')

    def test_change_access(self):
        self.add_acl()
        url = reverse('change-access', kwargs=self.kw_project)
        self.project.add_user(self.user, '@Administration')

        if 'weblate.billing' in settings.INSTALLED_APPS:
            # No permissions
            response = self.client.post(url, {'access_control': 0})
            self.assertEqual(response.status_code, 403)

            # Allow editing by creating billing plan
            from weblate.billing.models import Plan, Billing
            plan = Plan.objects.create()
            billing = Billing.objects.create(plan=plan)
            billing.projects.add(self.project)

        # Editing should now work
        response = self.client.post(
            url,
            {'access_control': Project.ACCESS_PROTECTED}
        )
        self.assertRedirects(response, self.access_url)

        # Verify change has been done
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.access_control, Project.ACCESS_PROTECTED)

    def test_acl_groups(self):
        """Test handling of ACL groups.
        """
        if 'weblate.billing' in settings.INSTALLED_APPS:
            billing_group = 1
        else:
            billing_group = 0
        match = '{}@'.format(self.project.name)
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.enable_review = False
        self.project.save()
        self.assertEqual(
            1, Group.objects.filter(name__startswith=match).count()
        )
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.enable_review = True
        self.project.save()
        self.assertEqual(
            8 + billing_group,
            Group.objects.filter(name__startswith=match).count()
        )
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.enable_review = True
        self.project.save()
        self.assertEqual(
            8 + billing_group,
            Group.objects.filter(name__startswith=match).count()
        )
        self.project.access_control = Project.ACCESS_CUSTOM
        self.project.save()
        self.assertEqual(
            0, Group.objects.filter(name__startswith=match).count()
        )
        self.project.access_control = Project.ACCESS_CUSTOM
        self.project.save()
        self.assertEqual(
            0, Group.objects.filter(name__startswith=match).count()
        )
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.assertEqual(
            8 + billing_group,
            Group.objects.filter(name__startswith=match).count()
        )
        self.project.delete()
        self.assertEqual(
            0, Group.objects.filter(name__startswith=match).count()
        )
