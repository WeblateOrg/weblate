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

from django.core.files import File
from django.urls import reverse

from rest_framework.test import APITestCase

from weblate.auth.models import User, Group
from weblate.screenshots.models import Screenshot
from weblate.trans.models import Project, Change, Unit, Source
from weblate.trans.tests.utils import RepoTestMixin, get_test_file

TEST_PO = get_test_file('cs.po')
TEST_SCREENSHOT = get_test_file('screenshot.png')


class APIBaseTest(APITestCase, RepoTestMixin):
    def setUp(self):
        self.clone_test_repos()
        self.component = self.create_component()
        self.translation_kwargs = {
            'language__code': 'cs',
            'component__slug': 'test',
            'component__project__slug': 'test'
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

    def create_acl(self):
        project = Project.objects.create(
            name='ACL',
            slug='acl',
            access_control=Project.ACCESS_PRIVATE,
        )
        self._create_component(
            'po-mono',
            'po-mono/*.po',
            'po-mono/en.po',
            project=project,
        )

    def authenticate(self, superuser=False):
        if self.user.is_superuser != superuser:
            self.user.is_superuser = superuser
            self.user.save()
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

    def test_changes(self):
        request = self.do_request(
            'api:project-changes',
            self.project_kwargs,
        )
        self.assertEqual(request.data['count'], 8)

    def test_statistics(self):
        request = self.do_request(
            'api:project-statistics',
            self.project_kwargs,
        )
        self.assertEqual(len(request.data), 3)


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
        self.component.new_base = 'po/cs.po'
        self.component.save()
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
        self.component.format = 'po-mono'
        self.component.filemask = 'po-mono/*.po'
        self.component.template = 'po-mono/en.po'
        self.component.save()
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

    def test_changes(self):
        request = self.do_request(
            'api:component-changes',
            self.component_kwargs,
        )
        self.assertEqual(request.data['count'], 8)


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
            response, 'Project-Id-Version: Weblate Hello World 2016'
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
        self.user.groups.clear()
        response = self.client.put(
            reverse(
                'api:translation-file',
                kwargs=self.translation_kwargs
            ),
            {'file': open(TEST_PO, 'rb')},
        )
        self.assertEqual(response.status_code, 404)

    def test_upload(self):
        self.authenticate()
        with open(TEST_PO, 'rb') as handle:
            response = self.client.put(
                reverse(
                    'api:translation-file',
                    kwargs=self.translation_kwargs
                ),
                {'file': handle},
            )
        self.assertEqual(
            response.data,
            {
                'accepted': 1,
                'count': 5,
                'not_found': 0,
                'result': True,
                'skipped': 0,
                'total': 5
            }
        )

    def test_upload_content(self):
        self.authenticate()
        with open(TEST_PO, 'rb') as handle:
            response = self.client.put(
                reverse(
                    'api:translation-file',
                    kwargs=self.translation_kwargs
                ),
                {'file': handle.read()},
            )
        self.assertEqual(response.status_code, 400)

    def test_upload_overwrite(self):
        self.test_upload()
        response = self.client.put(
            reverse(
                'api:translation-file',
                kwargs=self.translation_kwargs
            ),
            {'file': open(TEST_PO, 'rb'), 'overwrite': 1},
        )
        self.assertEqual(
            response.data,
            {
                'accepted': 1,
                'count': 5,
                'not_found': 0,
                'result': True,
                'skipped': 0,
                'total': 5
            }
        )

    def test_upload_invalid(self):
        self.authenticate()
        response = self.client.put(
            reverse(
                'api:translation-file',
                kwargs=self.translation_kwargs
            ),
        )
        self.assertEqual(response.status_code, 400)

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

    def test_changes(self):
        request = self.do_request(
            'api:translation-changes',
            self.translation_kwargs,
        )
        self.assertEqual(request.data['count'], 5)

    def test_units(self):
        request = self.do_request(
            'api:translation-units',
            self.translation_kwargs,
        )
        self.assertEqual(request.data['count'], 4)


class UnitAPITest(APIBaseTest):
    def test_list_units(self):
        response = self.client.get(
            reverse('api:unit-list')
        )
        self.assertEqual(response.data['count'], 12)

    def test_get_unit(self):
        response = self.client.get(
            reverse(
                'api:unit-detail',
                kwargs={'pk': Unit.objects.all()[0].pk}
            )
        )
        self.assertIn(
            'translation',
            response.data,
        )


class SourceAPITest(APIBaseTest):
    def test_list_sources(self):
        response = self.client.get(
            reverse('api:source-list')
        )
        self.assertEqual(response.data['count'], 4)

    def test_get_source(self):
        response = self.client.get(
            reverse(
                'api:source-detail',
                kwargs={'pk': Source.objects.all()[0].pk}
            )
        )
        self.assertIn(
            'component',
            response.data,
        )


class ScreenshotAPITest(APIBaseTest):
    def setUp(self):
        super(ScreenshotAPITest, self).setUp()
        shot = Screenshot.objects.create(
            name='Obrazek',
            component=self.component
        )
        with open(TEST_SCREENSHOT, 'rb') as handle:
            shot.image.save('screenshot.png', File(handle))

    def test_list_screenshots(self):
        response = self.client.get(
            reverse('api:screenshot-list')
        )
        self.assertEqual(response.data['count'], 1)

    def test_get_screenshot(self):
        response = self.client.get(
            reverse(
                'api:screenshot-detail',
                kwargs={'pk': Screenshot.objects.all()[0].pk}
            )
        )
        self.assertIn(
            'file_url',
            response.data,
        )

    def test_download(self):
        response = self.client.get(
            reverse(
                'api:screenshot-file',
                kwargs={'pk': Screenshot.objects.all()[0].pk}
            )
        )
        self.assertContains(
            response, b'PNG',
        )

    def test_upload(self, superuser=True, code=200, filename=TEST_SCREENSHOT):
        self.authenticate(superuser)
        Screenshot.objects.all()[0].image.delete()

        self.assertEqual(Screenshot.objects.all()[0].image, '')
        with open(filename, 'rb') as handle:
            response = self.client.post(
                reverse(
                    'api:screenshot-file',
                    kwargs={
                        'pk': Screenshot.objects.all()[0].pk,
                    }
                ),
                {
                    'image': handle,
                }
            )
        self.assertEqual(response.status_code, code)
        if code == 200:
            self.assertTrue(response.data['result'])

            self.assertIn('.png', Screenshot.objects.all()[0].image.path)

    def test_upload_denied(self):
        self.test_upload(False, 403)

    def test_upload_invalid(self):
        self.test_upload(True, 400, TEST_PO)


class ChangeAPITest(APIBaseTest):
    def test_list_changes(self):
        response = self.client.get(
            reverse('api:change-list')
        )
        self.assertEqual(response.data['count'], 8)

    def test_get_change(self):
        response = self.client.get(
            reverse(
                'api:change-detail',
                kwargs={'pk': Change.objects.all()[0].pk}
            )
        )
        self.assertIn(
            'translation',
            response.data,
        )


class MetricsAPITest(APIBaseTest):
    def test_metrics(self):
        self.authenticate()
        response = self.client.get(reverse('api:metrics'))
        self.assertEqual(response.data['projects'], 1)

    def test_forbidden(self):
        response = self.client.get(reverse('api:metrics'))
        self.assertEqual(response.data['detail'].code, 'not_authenticated')
