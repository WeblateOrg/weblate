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

from django.conf import settings
from django.test.client import RequestFactory
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
import shutil
import os
from weblate.trans.models import (
    Project, SubProject
)
from weblate.trans.tests.test_models import RepoTestCase


class ViewTestCase(RepoTestCase):
    def setUp(self):
        super(RepoTestCase, self).setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        # Create project to have some test base
        self.subproject = self.create_subproject()

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


class FeedViewTest(ViewTestCase):
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
