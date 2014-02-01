# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
Tests for charts and widgets.
"""

from weblate.trans.tests.test_views import ViewTestCase
from django.core.urlresolvers import reverse


class ChartsTest(ViewTestCase):
    '''
    Testing of charts.
    '''
    def test_activity_html(self):
        '''
        Test of html for activity charts.
        '''
        response = self.client.get(
            reverse('view_activity')
        )
        self.assertContains(response, 'img src="/activity')

        response = self.client.get(
            reverse('view_activity_project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'img src="/activity')

        response = self.client.get(
            reverse('view_activity_subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'img src="/activity')

        response = self.client.get(
            reverse('view_activity_translation', kwargs=self.kw_translation)
        )
        self.assertContains(response, 'img src="/activity')

        response = self.client.get(
            reverse('view_language_activity', kwargs={'lang': 'cs'})
        )
        self.assertContains(response, 'img src="/activity')

    def test_activity_monthly(self):
        '''
        Test of monthly activity charts.
        '''
        response = self.client.get(
            reverse('monthly_activity')
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('monthly_activity_project', kwargs=self.kw_project)
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('monthly_activity_subproject', kwargs=self.kw_subproject)
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('monthly_activity_translation', kwargs=self.kw_translation)
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('monthly_language_activity', kwargs={'lang': 'cs'})
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse(
                'monthly_user_activity',
                kwargs={'user': self.user.username}
            )
        )
        self.assertPNG(response)

    def test_activity_yearly(self):
        '''
        Test of yearly activity charts.
        '''
        response = self.client.get(
            reverse('yearly_activity')
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('yearly_activity_project', kwargs=self.kw_project)
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('yearly_activity_subproject', kwargs=self.kw_subproject)
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('yearly_activity_translation', kwargs=self.kw_translation)
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse('yearly_language_activity', kwargs={'lang': 'cs'})
        )
        self.assertPNG(response)

        response = self.client.get(
            reverse(
                'yearly_user_activity',
                kwargs={'user': self.user.username}
            )
        )
        self.assertPNG(response)
