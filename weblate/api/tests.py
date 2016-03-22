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

from django.core.urlresolvers import reverse

from rest_framework.test import APITestCase

from weblate.trans.tests.utils import RepoTestMixin


class APITest(APITestCase, RepoTestMixin):
    def setUp(self):
        self.clone_test_repos()
        self.subproject = self.create_subproject()

    def test_list_projects(self):
        response = self.client.get(
            reverse('api:project-list')
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'test')

    def test_list_components(self):
        response = self.client.get(
            reverse('api:subproject-list')
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'test')
        self.assertEqual(response.data[0]['project']['slug'], 'test')

    def test_list_translations(self):
        response = self.client.get(
            reverse('api:translation-list')
        )
        self.assertEqual(len(response.data), 3)

    def test_list_languages(self):
        response = self.client.get(
            reverse('api:language-list')
        )
        self.assertEqual(len(response.data), 3)
