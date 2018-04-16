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

"""Test for charts and widgets."""

import json

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class ChartsTest(FixtureTestCase):
    """Testing of charts."""
    def assert_json_chart_data(self, response):
        """Test whether response has valid json chart data."""
        self.assertEqual(response.get('Content-Type'), 'application/json')
        data = json.loads(response.content.decode('utf-8'))
        self.assertTrue('series' in data)
        self.assertTrue('labels' in data)

    def test_activity_monthly(self):
        """Test of monthly activity charts."""
        response = self.client.get(
            reverse('monthly_activity')
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('monthly_activity', kwargs=self.kw_project)
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('monthly_activity', kwargs=self.kw_component)
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('monthly_activity', kwargs=self.kw_translation)
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('monthly_activity', kwargs={'lang': 'cs'})
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse(
                'monthly_activity',
                kwargs={'user': self.user.username}
            )
        )
        self.assert_json_chart_data(response)

    def test_activity_yearly(self):
        """Test of yearly activity charts."""
        response = self.client.get(
            reverse('yearly_activity')
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('yearly_activity', kwargs=self.kw_project)
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('yearly_activity', kwargs=self.kw_component)
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('yearly_activity', kwargs=self.kw_translation)
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse('yearly_activity', kwargs={'lang': 'cs'})
        )
        self.assert_json_chart_data(response)

        response = self.client.get(
            reverse(
                'yearly_activity',
                kwargs={'user': self.user.username}
            )
        )
        self.assert_json_chart_data(response)
