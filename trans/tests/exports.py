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
Tests for data exports.
"""

from django.core.urlresolvers import reverse
from django.utils import simplejson
from trans.tests.views import ViewTestCase


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
            reverse('export_stats', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        parsed = simplejson.loads(response.content)
        self.assertEqual(parsed[0]['name'], 'Czech')
