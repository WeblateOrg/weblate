# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
from django.contrib.auth.models import Group, User
from weblate.trans.tests.test_views import ViewTestCase


class ACLViewTest(ViewTestCase):
    def setUp(self):
        super(ACLViewTest, self).setUp()
        self.project.enable_acl = True
        self.project.save()

    def add_acl(self):
        """
        Adds user to ACL.
        """
        self.project.add_user(self.user)

    def make_admin(self):
        """
        Makes user a Manager.
        """
        group = Group.objects.get(name='Managers')
        self.user.groups.add(group)

    def test_acl_denied(self):
        """No access to the project without ACL.
        """
        response = self.client.get(
            reverse('project', kwargs=self.kw_project)
        )
        self.assertEquals(response.status_code, 403)

    def test_acl(self):
        """Regular user should not have access to user management.
        """
        self.add_acl()
        response = self.client.get(
            reverse('project', kwargs=self.kw_project)
        )
        self.assertNotContains(response, 'Manage users')

    def test_edit_acl(self):
        """Manager should have access to user management.
        """
        self.add_acl()
        self.make_admin()
        response = self.client.get(
            reverse('project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Manage users')

    def test_add_acl(self):
        """Adding and removing user from the ACL project.
        """
        self.add_acl()
        self.make_admin()
        project_url = reverse('project', kwargs=self.kw_project)
        second_user = User.objects.create_user(
            'seconduser',
            'noreply@example.org',
            'testpassword'
        )

        # Add user
        response = self.client.post(
            reverse('add-user', kwargs=self.kw_project),
            {'name': second_user.username}
        )
        self.assertRedirects(response, '{0}#acl'.format(project_url))

        # Ensure user is now listed
        response = self.client.get(project_url)
        self.assertContains(response, second_user.username)
        self.assertContains(response, second_user.email)

        # Remove user
        response = self.client.post(
            reverse('delete-user', kwargs=self.kw_project),
            {'name': second_user.username}
        )
        self.assertRedirects(response, '{0}#acl'.format(project_url))

        # Ensure user is now not listed
        response = self.client.get(project_url)
        self.assertNotContains(response, second_user.username)
        self.assertNotContains(response, second_user.email)
