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
from django.utils import simplejson
from weblate.trans.tests.test_models import RepoTestCase
from weblate.accounts.models import Profile


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
        self.client.login(username='testuser', password='testpassword')

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


class BasicViewTest(ViewTestCase):
    def test_view_home(self):
        response = self.client.get(
            reverse('home')
        )
        self.assertContains(response, 'Test/Test')

    def test_view_project(self):
        response = self.client.get(
            reverse('project', kwargs={
                'project': self.subproject.project.slug
            })
        )
        self.assertContains(response, 'Test/Test')

    def test_view_subproject(self):
        response = self.client.get(
            reverse('subproject', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        self.assertContains(response, 'Test/Test')

    def test_view_translation(self):
        response = self.client.get(
            reverse('translation', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
                'lang': 'cs',
            })
        )
        self.assertContains(response, 'Test/Test')


class ExportsViewTest(ViewTestCase):
    def test_view_rss(self):
        response = self.client.get(
            reverse('rss')
        )
        self.assertContains(response, 'Test/Test')

    def test_view_rss_project(self):
        response = self.client.get(
            reverse('rss-project', kwargs={
                'project': self.subproject.project.slug
            })
        )
        self.assertContains(response, 'Test/Test')

    def test_view_rss_subproject(self):
        response = self.client.get(
            reverse('rss-subproject', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        self.assertContains(response, 'Test/Test')

    def test_view_rss_translation(self):
        response = self.client.get(
            reverse('rss-translation', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
                'lang': 'cs',
            })
        )
        self.assertContains(response, 'Test/Test')

    def test_export_stats(self):
        response = self.client.get(
            reverse('export-stats', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        parsed = simplejson.loads(response.content)
        self.assertEqual(parsed[0]['name'], 'Czech')


class EditTest(ViewTestCase):
    '''
    Tests for manipulating translation.
    '''
    def edit_unit(self, source, target):
        translation = self.subproject.translation_set.get(language_code='cs')
        unit = translation.unit_set.get(source=source)
        translate_url = reverse('translate', kwargs={
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': 'cs',
        })
        return self.client.post(
            translate_url,
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
        self.assertRedirects(response, translate_url + '?type=all&pos=1')
        unit = translation.unit_set.get(source='Hello, world!\n')
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)

    def test_edit_check(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!'
        )
        # We should stay on current message
        self.assertRedirects(response, translate_url + '?type=all&pos=1&dir=stay')
        unit = translation.unit_set.get(source='Hello, world!\n')
        self.assertEqual(unit.target, 'Nazdar svete!')
        self.assertEqual(len(unit.checks()), 2)
