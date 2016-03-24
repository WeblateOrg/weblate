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


class APIBaseTest(APITestCase, RepoTestMixin):
    def setUp(self):
        self.clone_test_repos()
        self.subproject = self.create_subproject()
        self.translation_kwargs = {
            'language__code': 'cs',
            'subproject__slug': 'test',
            'subproject__project__slug': 'test'
        }
        self.component_kwargs = {
            'slug': 'test',
            'project__slug': 'test'
        }
        self.project_kwargs = {
            'slug': 'test'
        }


class APITest(APIBaseTest):
    def test_list_projects(self):
        response = self.client.get(
            reverse('api:project-list')
        )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['slug'], 'test')

    def test_get_project(self):
        response = self.client.get(
            reverse('api:project-detail', kwargs=self.project_kwargs)
        )
        self.assertEqual(response.data['slug'], 'test')

    def test_list_components(self):
        response = self.client.get(
            reverse('api:component-list')
        )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['slug'], 'test')
        self.assertEqual(
            response.data['results'][0]['project']['slug'], 'test'
        )

    def test_get_component(self):
        response = self.client.get(
            reverse(
                'api:component-detail',
                kwargs=self.component_kwargs
            )
        )
        self.assertEqual(response.data['slug'], 'test')
        self.assertEqual(response.data['project']['slug'], 'test')

    def test_list_translations(self):
        response = self.client.get(
            reverse('api:translation-list')
        )
        self.assertEqual(response.data['count'], 3)

    def test_get_translation(self):
        response = self.client.get(
            reverse(
                'api:translation-detail',
                kwargs=self.translation_kwargs
            )
        )
        self.assertEqual(response.data['language_code'], 'cs')

    def test_list_languages(self):
        response = self.client.get(
            reverse('api:language-list')
        )
        self.assertEqual(response.data['count'], 3)

    def test_get_language(self):
        response = self.client.get(
            reverse('api:language-detail', kwargs={'code': 'cs'})
        )
        self.assertEqual(response.data['name'], 'Czech')


class TranslationAPITest(APIBaseTest):
    def test_download(self):
        response = self.client.get(
            reverse(
                'api:translation-download',
                kwargs=self.translation_kwargs
            )
        )
        self.assertContains(
            response, 'Project-Id-Version: Weblate Hello World 2012'
        )

    def test_download_format(self):
        args = {'format': 'xliff'}
        args.update(self.translation_kwargs)
        response = self.client.get(
            reverse(
                'api:translation-download',
                kwargs=args
            )
        )
        self.assertContains(
            response, '<xliff'
        )
