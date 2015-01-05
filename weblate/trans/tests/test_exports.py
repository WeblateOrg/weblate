# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
import json
from weblate.trans.tests.test_views import ViewTestCase


class ExportsViewTest(ViewTestCase):
    def test_view_rss(self):
        response = self.client.get(
            reverse('rss')
        )
        self.assertContains(response, 'Test/Test')

    def test_view_rss_project(self):
        response = self.client.get(
            reverse('rss-project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_rss_subproject(self):
        response = self.client.get(
            reverse('rss-subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_rss_translation(self):
        response = self.client.get(
            reverse('rss-translation', kwargs=self.kw_translation)
        )
        self.assertContains(response, 'Test/Test')

    def test_export_stats(self):
        response = self.client.get(
            reverse('export_stats', kwargs=self.kw_subproject)
        )
        parsed = json.loads(response.content)
        self.assertEqual(parsed[0]['name'], 'Czech')

    def test_export_stats_jsonp(self):
        response = self.client.get(
            reverse('export_stats', kwargs=self.kw_subproject),
            {'jsonp': 'test_callback'}
        )
        self.assertContains(response, 'test_callback(')

    def test_data(self):
        response = self.client.get(
            reverse('data_root')
        )
        self.assertContains(response, 'Test')
        response = self.client.get(
            reverse('data_project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Test')

    def test_about(self):
        response = self.client.get(
            reverse('about')
        )
        self.assertContains(response, 'Translate Toolkit')
