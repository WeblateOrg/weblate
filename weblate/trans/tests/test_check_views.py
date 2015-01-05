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
Tests for check views.
"""

from weblate.trans.tests.test_views import ViewTestCase
from django.core.urlresolvers import reverse


class ChecksViewTest(ViewTestCase):
    '''
    Testing of check views.
    '''
    def test_browse(self):
        response = self.client.get(reverse('checks'))
        self.assertContains(response, '/same/')

        response = self.client.get(
            reverse('show_check', kwargs={'name': 'same'})
        )
        self.assertContains(response, '/same/')

        response = self.client.get(
            reverse('show_check', kwargs={'name': 'ellipsis'})
        )
        self.assertContains(response, u'…')

        response = self.client.get(
            reverse('show_check', kwargs={'name': 'not-existing'})
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(
            reverse(
                'show_check_project',
                kwargs={'name': 'same', 'project': self.project.slug}
            )
        )
        self.assertContains(response, '/same/')

        response = self.client.get(
            reverse(
                'show_check_project',
                kwargs={'name': 'ellipsis', 'project': self.project.slug}
            )
        )
        self.assertContains(response, u'…')

        response = self.client.get(
            reverse(
                'show_check_project',
                kwargs={'name': 'non-existing', 'project': self.project.slug}
            )
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(
            reverse(
                'show_check_subproject',
                kwargs={
                    'name': 'same',
                    'project': self.project.slug,
                    'subproject': self.subproject.slug,
                }
            )
        )
        self.assertContains(response, '/same/')

        response = self.client.get(
            reverse(
                'show_check_subproject',
                kwargs={
                    'name': 'ellipsis',
                    'project': self.project.slug,
                    'subproject': self.subproject.slug,
                }
            )
        )
        self.assertRedirects(
            response,
            '{0}?type=ellipsis'.format(
                reverse('review_source', kwargs={
                    'project': self.project.slug,
                    'subproject': self.subproject.slug,
                })
            )
        )

        response = self.client.get(
            reverse(
                'show_check_subproject',
                kwargs={
                    'name': 'non-existing',
                    'project': self.project.slug,
                    'subproject': self.subproject.slug,
                }
            )
        )
        self.assertEqual(response.status_code, 404)
