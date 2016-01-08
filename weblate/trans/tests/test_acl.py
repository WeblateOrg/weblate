# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for ACL management.
"""

from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from weblate.trans.tests.test_views import ViewTestCase


class ACLViewTest(ViewTestCase):
    def setUp(self):
        super(ACLViewTest, self).setUp()
        self.project.enable_acl = True
        self.project.save()
        self.project_url = reverse('project', kwargs=self.kw_project)
        self.second_user = User.objects.create_user(
            'seconduser',
            'noreply@example.org',
            'testpassword'
        )

    def add_acl(self):
        """
        Adds user to ACL.
        """
        self.project.add_user(self.user)

    def test_acl_denied(self):
        """No access to the project without ACL.
        """
        response = self.client.get(self.project_url)
        self.assertEqual(response.status_code, 403)

    def test_acl(self):
        """Regular user should not have access to user management.
        """
        self.add_acl()
        response = self.client.get(self.project_url)
        self.assertNotContains(response, 'Manage users')

    def test_edit_acl(self):
        """Manager should have access to user management.
        """
        self.add_acl()
        self.make_manager()
        response = self.client.get(self.project_url)
        self.assertContains(response, 'Manage users')

    def test_edit_acl_owner(self):
        """Owner should have access to user management.
        """
        self.add_acl()
        self.project.owners.add(self.user)
        response = self.client.get(self.project_url)
        self.assertContains(response, 'Manage users')

    def add_user(self):
        self.add_acl()
        self.project.owners.add(self.user)

        # Add user
        response = self.client.post(
            reverse('add-user', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.assertRedirects(response, '{0}#acl'.format(self.project_url))

        # Ensure user is now listed
        response = self.client.get(self.project_url)
        self.assertContains(response, self.second_user.username)
        self.assertContains(response, self.second_user.email)

    def remove_user(self):
        # Remove user
        response = self.client.post(
            reverse('delete-user', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.assertRedirects(response, '{0}#acl'.format(self.project_url))

        # Ensure user is now not listed
        response = self.client.get(self.project_url)
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
            reverse('make-owner', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.assertTrue(
            self.project.owners.filter(
                username=self.second_user.username
            ).exists()
        )
        self.client.post(
            reverse('revoke-owner', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.assertFalse(
            self.project.owners.filter(
                username=self.second_user.username
            ).exists()
        )
        self.remove_user()

    def test_delete_owner(self):
        """Adding and deleting owner from the ACL project.
        """
        self.add_user()
        self.client.post(
            reverse('make-owner', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.remove_user()
        self.assertFalse(
            self.project.owners.filter(
                username=self.second_user.username
            ).exists()
        )

    def test_denied_owner_delete(self):
        """Test that deleting last owner does not work."""
        self.project.owners.add(self.user)
        self.client.post(
            reverse('revoke-owner', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.assertTrue(
            self.project.owners.filter(
                username=self.user.username
            ).exists()
        )
        self.client.post(
            reverse('delete-user', kwargs=self.kw_project),
            {'name': self.second_user.username}
        )
        self.assertTrue(
            self.project.owners.filter(
                username=self.user.username
            ).exists()
        )

    def test_nonexisting_user(self):
        """Test adding non existing user."""
        self.project.owners.add(self.user)
        response = self.client.post(
            reverse('add-user', kwargs=self.kw_project),
            {'name': 'nonexisging'},
            follow=True
        )
        self.assertContains(response, 'No matching user found!')
