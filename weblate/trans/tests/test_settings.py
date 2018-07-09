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

"""Test for settings management."""

from django.urls import reverse

from weblate.trans.models import Project, Component
from weblate.trans.tests.test_views import ViewTestCase


class SettingsTest(ViewTestCase):
    def test_project_denied(self):
        url = reverse('settings', kwargs=self.kw_project)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_project(self):
        self.project.add_user(self.user, '@Administration')
        url = reverse('settings', kwargs=self.kw_project)
        response = self.client.get(url)
        self.assertContains(response, 'Settings')
        data = response.context['settings_form'].initial
        data['web'] = 'https://example.com/test/'
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'Settings saved')
        self.assertEqual(
            Project.objects.get(pk=self.project.pk).web,
            'https://example.com/test/'
        )

    def test_component_denied(self):
        url = reverse('settings', kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_component(self):
        self.project.add_user(self.user, '@Administration')
        url = reverse('settings', kwargs=self.kw_component)
        response = self.client.get(url)
        self.assertContains(response, 'Settings')
        data = {}
        data.update(response.context['form'].initial)
        data['license_url'] = 'https://example.com/test/'
        data['license'] = 'test'
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'Settings saved')
        self.assertEqual(
            Component.objects.get(pk=self.component.pk).license_url,
            'https://example.com/test/'
        )
