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

from django.contrib.auth.models import User, Group
from django.core.cache import cache
from django.core.urlresolvers import reverse

from rest_framework.test import APITestCase

from weblate.trans.models.project import Project, get_acl_cache_key
from weblate.trans.tests.utils import RepoTestMixin, get_test_file

TEST_PO = get_test_file('cs.po')


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
        self.tearDown()
        self.user = User.objects.create_user(
            'apitest',
            'apitest@example.org',
            'x',
        )
        group = Group.objects.get(name='Users')
        self.user.groups.add(group)

    def tearDown(self):
        cache.delete(get_acl_cache_key(None))

    def create_acl(self):
        project = Project.objects.create(
            name='ACL',
            slug='acl',
            enable_acl=True,
        )
        self._create_subproject(
            'po-mono',
            'po-mono/*.po',
            'po-mono/en.po',
            project=project,
        )

    def authenticate(self, superuser=False):
        if self.user.is_superuser != superuser:
            self.user.is_superuser = superuser
            self.user.save()
        cache.delete(get_acl_cache_key(self.user))
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )

    def do_request(self, name, kwargs, data=None, code=200, superuser=False,
                   get=True, request=None, skip=()):
        self.authenticate(superuser)
        url = reverse(name, kwargs=kwargs)
        if get:
            response = self.client.get(url)
        else:
            response = self.client.post(url, request)
        self.assertEqual(response.status_code, code)
        if data is not None:
            for item in skip:
                del response.data[item]
            self.assertEqual(response.data, data)
        return response


class ProjectAPITest(APIBaseTest):
    def test_list_projects(self):
        response = self.client.get(
            reverse('api:project-list')
        )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['slug'], 'test')

    def test_list_projects_acl(self):
        self.create_acl()
        response = self.client.get(
            reverse('api:project-list')
        )
        self.assertEqual(response.data['count'], 1)
        self.authenticate(True)
        response = self.client.get(
            reverse('api:project-list')
        )
        self.assertEqual(response.data['count'], 2)

    def test_get_project(self):
        response = self.client.get(
            reverse('api:project-detail', kwargs=self.project_kwargs)
        )
        self.assertEqual(response.data['slug'], 'test')

    def test_repo_op_denied(self):
        for operation in ('push', 'pull', 'reset', 'commit'):
            self.do_request(
                'api:project-repository',
                self.project_kwargs,
                code=403,
                get=False,
                request={'operation': operation},
            )

    def test_repo_ops(self):
        for operation in ('push', 'pull', 'reset', 'commit'):
            self.do_request(
                'api:project-repository',
                self.project_kwargs,
                get=False,
                superuser=True,
                request={'operation': operation},
            )

    def test_repo_invalid(self):
        self.do_request(
            'api:project-repository',
            self.project_kwargs,
            code=400,
            get=False,
            superuser=True,
            request={'operation': 'invalid'},
        )

    def test_repo_status_denied(self):
        self.do_request(
            'api:project-repository',
            self.project_kwargs,
            code=403
        )

    def test_repo_status(self):
        self.do_request(
            'api:project-repository',
            self.project_kwargs,
            superuser=True,
            data={
                'needs_push': False,
                'needs_merge': False,
                'needs_commit': False
            },
            skip=('url',),
        )

    def test_components(self):
        request = self.do_request(
            'api:project-components',
            self.project_kwargs,
        )
        self.assertEqual(request.data['count'], 1)


class ComponentAPITest(APIBaseTest):
    def test_list_components(self):
        response = self.client.get(
            reverse('api:component-list')
        )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['slug'], 'test')
        self.assertEqual(
            response.data['results'][0]['project']['slug'], 'test'
        )

    def test_list_components_acl(self):
        self.create_acl()
        response = self.client.get(
            reverse('api:component-list')
        )
        self.assertEqual(response.data['count'], 1)
        self.authenticate(True)
        response = self.client.get(
            reverse('api:component-list')
        )
        self.assertEqual(response.data['count'], 2)

    def test_get_component(self):
        response = self.client.get(
            reverse(
                'api:component-detail',
                kwargs=self.component_kwargs
            )
        )
        self.assertEqual(response.data['slug'], 'test')
        self.assertEqual(response.data['project']['slug'], 'test')

    def test_get_lock(self):
        response = self.client.get(
            reverse(
                'api:component-lock',
                kwargs=self.component_kwargs
            )
        )
        self.assertEqual(response.data, {'locked': False})

    def test_set_lock_denied(self):
        self.authenticate()
        url = reverse(
            'api:component-lock',
            kwargs=self.component_kwargs
        )
        response = self.client.post(url, {'lock': True})
        self.assertEqual(response.status_code, 403)

    def test_set_lock(self):
        self.authenticate(True)
        url = reverse(
            'api:component-lock',
            kwargs=self.component_kwargs
        )
        response = self.client.get(url)
        self.assertEqual(response.data, {'locked': False})
        response = self.client.post(url, {'lock': True})
        self.assertEqual(response.data, {'locked': True})
        response = self.client.post(url, {'lock': False})
        self.assertEqual(response.data, {'locked': False})

    def test_repo_status_denied(self):
        self.do_request(
            'api:component-repository',
            self.component_kwargs,
            code=403
        )

    def test_repo_status(self):
        self.do_request(
            'api:component-repository',
            self.component_kwargs,
            superuser=True,
            data={
                'needs_push': False,
                'needs_merge': False,
                'needs_commit': False,
                'merge_failure': None,
            },
            skip=('remote_commit', 'status', 'url'),
        )

    def test_statistics(self):
        self.do_request(
            'api:component-statistics',
            self.component_kwargs,
            data={
                'count': 3,
            },
            skip=('results', 'previous', 'next'),
        )

    def test_new_template_404(self):
        self.do_request(
            'api:component-new-template',
            self.component_kwargs,
            code=404,
        )

    def test_new_template(self):
        self.subproject.new_base = 'po/cs.po'
        self.subproject.save()
        self.do_request(
            'api:component-new-template',
            self.component_kwargs,
        )

    def test_monolingual_404(self):
        self.do_request(
            'api:component-monolingual-base',
            self.component_kwargs,
            code=404,
        )

    def test_monolingual(self):
        self.subproject.format = 'po-mono'
        self.subproject.filemask = 'po-mono/*.po'
        self.subproject.template = 'po-mono/en.po'
        self.subproject.save()
        self.do_request(
            'api:component-monolingual-base',
            self.component_kwargs,
        )

    def test_translations(self):
        request = self.do_request(
            'api:component-translations',
            self.component_kwargs,
        )
        self.assertEqual(request.data['count'], 3)


class LanguageAPITest(APIBaseTest):
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
    def test_list_translations(self):
        response = self.client.get(
            reverse('api:translation-list')
        )
        self.assertEqual(response.data['count'], 3)

    def test_list_translations_acl(self):
        self.create_acl()
        response = self.client.get(
            reverse('api:translation-list')
        )
        self.assertEqual(response.data['count'], 3)
        self.authenticate(True)
        response = self.client.get(
            reverse('api:translation-list')
        )
        self.assertEqual(response.data['count'], 7)

    def test_get_translation(self):
        response = self.client.get(
            reverse(
                'api:translation-detail',
                kwargs=self.translation_kwargs
            )
        )
        self.assertEqual(response.data['language_code'], 'cs')

    def test_download(self):
        response = self.client.get(
            reverse(
                'api:translation-file',
                kwargs=self.translation_kwargs
            )
        )
        self.assertContains(
            response, 'Project-Id-Version: Weblate Hello World 2012'
        )

    def test_download_invalid_format(self):
        args = {'format': 'invalid'}
        args.update(self.translation_kwargs)
        response = self.client.get(
            reverse(
                'api:translation-file',
                kwargs=args
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_download_format(self):
        args = {'format': 'xliff'}
        args.update(self.translation_kwargs)
        response = self.client.get(
            reverse(
                'api:translation-file',
                kwargs=args
            )
        )
        self.assertContains(
            response, '<xliff'
        )

    def test_upload_denied(self):
        self.authenticate()
        # Remove all permissions
        self.user.groups.all()[0].permissions.clear()
        response = self.client.put(
            reverse(
                'api:translation-file',
                kwargs=self.translation_kwargs
            ),
            {'file': open(TEST_PO, 'rb')},
        )
        self.assertEqual(response.status_code, 403)

    def test_upload(self):
        self.authenticate()
        response = self.client.put(
            reverse(
                'api:translation-file',
                kwargs=self.translation_kwargs
            ),
            {'file': open(TEST_PO, 'rb')},
        )
        self.assertEqual(
            response.data,
            {'count': 5, 'result': True}
        )

    def test_repo_status_denied(self):
        self.do_request(
            'api:translation-repository',
            self.translation_kwargs,
            code=403
        )

    def test_repo_status(self):
        self.do_request(
            'api:translation-repository',
            self.translation_kwargs,
            superuser=True,
            data={
                'needs_push': False,
                'needs_merge': False,
                'needs_commit': False,
                'merge_failure': None,
            },
            skip=('remote_commit', 'status', 'url'),
        )

    def test_statistics(self):
        self.do_request(
            'api:translation-statistics',
            self.translation_kwargs,
            data={
                'last_author': None,
                'code': 'cs',
                'failing_percent': 0.0,
                'url': 'http://example.com/engage/test/cs/',
                'translated_percent': 0.0,
                'total_words': 15,
                'failing': 0,
                'translated_words': 0,
                'url_translate': 'http://example.com/projects/test/test/cs/',
                'fuzzy_percent': 0.0,
                'translated': 0,
                'fuzzy': 0,
                'total': 4,
                'last_change': None,
                'name': 'Czech'
            }
        )
