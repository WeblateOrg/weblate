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

"""Test for creating projects and models."""

from __future__ import unicode_literals

from django.test.utils import modify_settings
from django.urls import reverse

import six

from weblate.trans.tests.utils import create_billing
from weblate.trans.tests.test_views import ViewTestCase


class CreateTest(ViewTestCase):

    def assert_create_project(self, result):
        response = self.client.get(reverse('create-project'))
        match = 'not have permission to create project'
        if result:
            self.assertNotContains(response, match)
        else:
            self.assertContains(response, match)

    def client_create_project(self, result, **kwargs):
        params = {
            'name': 'Create Project',
            'slug': 'create-project',
            'web': 'https://weblate.org/',
        }
        params.update(kwargs)
        response = self.client.post(reverse('create-project'), params)
        if isinstance(result, six.string_types):
            self.assertRedirects(response, result)
        elif result:
            self.assertEqual(response.status_code, 302)
        else:
            self.assertEqual(response.status_code, 200)
        return response

    @modify_settings(INSTALLED_APPS={'append': 'weblate.billing'})
    def test_create_project_billing(self):
        # No permissions without billing
        self.assert_create_project(False)
        self.client_create_project(reverse('create-project'))

        # Create empty billing
        billing = create_billing(self.user)
        self.assert_create_project(True)

        # Create one project
        self.client_create_project(False, billing=0)
        self.client_create_project(True, billing=billing.pk)

        # No more billings left
        self.client_create_project(
            reverse('create-project'),
            name='p2', slug='p2', billing=billing.pk
        )

    @modify_settings(INSTALLED_APPS={'remove': 'weblate.billing'})
    def test_create_project_admin(self):
        # No permissions without superuser
        self.assert_create_project(False)
        self.client_create_project(reverse('create-project'))

        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        # Now can create
        self.assert_create_project(True)
        self.client_create_project(True)
        self.client_create_project(True, name='p2', slug='p2')

    def assert_create_component(self, result):
        response = self.client.get(reverse('create-component'))
        match = 'not have permission to create component'
        if result:
            self.assertNotContains(response, match)
        else:
            self.assertContains(response, match)

    def client_create_component(self, result, **kwargs):
        params = {
            'name': 'Create Component',
            'slug': 'create-component',
            'project': self.project.pk,
            'vcs': 'git',
            'repo': self.component.get_repo_link_url(),
            'file_format': 'po',
            'filemask': 'po/*.po',
            'new_base': 'po/project.pot',
            'new_lang': 'add',
            'language_regex': '^[^.]+$',
        }
        params.update(kwargs)
        response = self.client.post(reverse('create-component'), params)
        if result:
            self.assertEqual(response.status_code, 302)
        else:
            self.assertEqual(response.status_code, 200)
        return response

    @modify_settings(INSTALLED_APPS={'append': 'weblate.billing'})
    def test_create_component_billing(self):
        # No permissions without billing
        self.assert_create_component(False)
        self.client_create_component(False)

        # Create billing and add permissions
        billing = create_billing(self.user)
        billing.projects.add(self.project)
        self.project.add_user(self.user, '@Administration')
        self.assert_create_component(True)

        # Create two components
        self.client_create_component(True)
        self.client_create_component(True, name='c2', slug='c2')

        # Restrict plan to test nothing more can be created
        billing.plan.limit_strings = 1
        billing.plan.save()

        self.client_create_component(False, name='c3', slug='c3')

    @modify_settings(INSTALLED_APPS={'remove': 'weblate.billing'})
    def test_create_component_admin(self):
        # No permissions without superuser
        self.assert_create_component(False)
        self.client_create_component(False)

        # Make superuser
        self.user.is_superuser = True
        self.user.save()

        # Now can create
        self.assert_create_component(True)
        self.client_create_component(True)
        self.client_create_component(True, name='c2', slug='c2')
