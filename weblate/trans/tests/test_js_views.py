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
Tests for AJAX/JS views.
"""

from weblate.trans.tests.test_views import ViewTestCase
from django.core.urlresolvers import reverse
import json


class JSViewsTest(ViewTestCase):
    '''
    Testing of AJAX/JS views.
    '''

    def test_get_string(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-get', kwargs={'checksum': unit.checksum}),
        )
        self.assertContains(response, 'Hello')
        self.assertEqual(response.content, unit.get_source_plurals()[0])

        response = self.client.get(
            reverse('js-get', kwargs={'checksum': 'x'}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, '')

    def test_get_detail(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-detail', kwargs={
                'checksum': unit.checksum,
                'subproject': unit.translation.subproject.slug,
                'project': unit.translation.subproject.project.slug,
            }),
        )
        self.assertContains(response, 'Czech')

    def test_translate(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-translate', kwargs={'unit_id': unit.id}),
            {'service': 'dummy'}
        )
        self.assertContains(response, 'Ahoj')
        data = json.loads(response.content)
        self.assertEqual(
            data['translations'],
            [
                {
                    'quality': 100,
                    'service': 'Dummy',
                    'text': u'Nazdar světe!',
                    'source': u'Hello, world!\n',
                },
                {
                    'quality': 100,
                    'service': 'Dummy',
                    'text': u'Ahoj světe!',
                    'source': u'Hello, world!\n',
                },
            ]
        )

        # Invalid service
        response = self.client.get(
            reverse('js-translate', kwargs={'unit_id': unit.id}),
            {'service': 'invalid'}
        )
        self.assertEqual(response.status_code, 400)

    def test_get_unit_changes(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-unit-changes', kwargs={'unit_id': unit.id}),
        )
        self.assertContains(response, 'href="/exports/rss/')

    def test_mt_services(self):
        response = self.client.get(reverse('js-mt-services'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Check we have dummy service listed
        self.assertIn('dummy', data)
