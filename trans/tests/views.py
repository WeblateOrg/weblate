# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
Tests for translation views.
"""

from django.test.client import RequestFactory
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
from trans.tests.models import RepoTestCase
from accounts.models import Profile
import cairo
from cStringIO import StringIO


class ViewTestCase(RepoTestCase):
    def setUp(self):
        super(ViewTestCase, self).setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        # Create profile for him
        Profile.objects.create(user=self.user)
        # Create project to have some test base
        self.subproject = self.create_subproject()
        self.project = self.subproject.project
        # Login
        self.client.login(username='testuser', password='testpassword')
        # Prepopulate kwargs
        self.kw_project = {
            'project': self.project.slug
        }
        self.kw_subproject = {
            'project': self.project.slug,
            'subproject': self.subproject.slug,
        }
        self.kw_translation = {
            'project': self.project.slug,
            'subproject': self.subproject.slug,
            'lang': 'cs',
        }
        self.kw_lang_project = {
            'project': self.project.slug,
            'lang': 'cs',
        }

        # Store URL for testing
        self.translation_url = self.get_translation().get_absolute_url()
        self.project_url = self.project.get_absolute_url()
        self.subproject_url = self.subproject.get_absolute_url()

    def get_request(self, *args, **kwargs):
        '''
        Wrapper to get fake request object.
        '''
        request = self.factory.get(*args, **kwargs)
        request.user = self.user
        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def get_translation(self):
        return self.subproject.translation_set.get(
            language_code='cs'
        )

    def get_unit(self):
        translation = self.get_translation()
        return translation.unit_set.get(source='Hello, world!\n')

    def change_unit(self, target):
        unit = self.get_unit()
        unit.target = target
        unit.save_backend(self.get_request('/'))

    def assertPNG(self, response):
        '''
        Checks whether response contains valid PNG image.
        '''
        # Check response status code
        self.assertEqual(response.status_code, 200)
        # Try to load PNG with Cairo
        cairo.ImageSurface.create_from_png(
            StringIO(response.content)
        )


class BasicViewTest(ViewTestCase):
    def test_view_home(self):
        response = self.client.get(
            reverse('home')
        )
        self.assertContains(response, 'Test/Test')

    def test_view_project(self):
        response = self.client.get(
            reverse('project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_subproject(self):
        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_translation(self):
        response = self.client.get(
            reverse('translation', kwargs=self.kw_translation)
        )
        self.assertContains(response, 'Test/Test')


class BasicResourceViewTest(BasicViewTest):
    def create_subproject(self, file_format='aresource',
                          mask='android/values-*/strings.xml',
                          template='android/values/strings.xml'):
        return super(BasicResourceViewTest, self).create_subproject(
            file_format,
            mask,
            template,
        )


class EditTest(ViewTestCase):
    '''
    Tests for manipulating translation.
    '''
    def setUp(self):
        super(EditTest, self).setUp()
        self.translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        self.translate_url = self.translation.get_translate_url()

    def edit_unit(self, source, target):
        unit = self.translation.unit_set.get(source=source)
        return self.client.post(
            self.translate_url,
            {
                'checksum': unit.checksum,
                'target': target,
                'type': 'all',
                'dir': 'forward',
                'pos': '1',
            }
        )

    def test_edit(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertRedirects(response, self.translate_url + '?type=all&pos=1')
        unit = self.translation.unit_set.get(source='Hello, world!\n')
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)

    def test_edit_check(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!'
        )
        # We should stay on current message
        self.assertRedirects(
            response, self.translate_url + '?type=all&pos=1&dir=stay'
        )
        unit = self.translation.unit_set.get(source='Hello, world!\n')
        self.assertEqual(unit.target, 'Nazdar svete!')
        self.assertEqual(len(unit.checks()), 2)

    def test_commit_push(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertRedirects(response, self.translate_url + '?type=all&pos=1')
        self.assertTrue(self.translation.git_needs_commit())
        self.assertTrue(self.subproject.git_needs_commit())
        self.assertTrue(self.subproject.project.git_needs_commit())

        self.translation.commit_pending()

        self.assertFalse(self.translation.git_needs_commit())
        self.assertFalse(self.subproject.git_needs_commit())
        self.assertFalse(self.subproject.project.git_needs_commit())

        self.assertTrue(self.translation.git_needs_push())
        self.assertTrue(self.subproject.git_needs_push())
        self.assertTrue(self.subproject.project.git_needs_push())

        self.translation.do_push()

        self.assertFalse(self.translation.git_needs_push())
        self.assertFalse(self.subproject.git_needs_push())
        self.assertFalse(self.subproject.project.git_needs_push())


class EditResourceTest(EditTest):
    def create_subproject(self, file_format='aresource',
                          mask='android/values-*/strings.xml',
                          template='android/values/strings.xml'):
        return super(EditResourceTest, self).create_subproject(
            file_format,
            mask,
            template,
        )
