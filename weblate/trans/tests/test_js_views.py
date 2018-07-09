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

"""Test for AJAX/JS views."""

from __future__ import unicode_literals

import json

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.classloader import load_class
from weblate.machinery import MACHINE_TRANSLATION_SERVICES


class JSViewsTest(FixtureTestCase):
    """Testing of AJAX/JS views."""
    @staticmethod
    def ensure_dummy_mt():
        """Ensure we have dummy mt installed"""
        if 'dummy' in MACHINE_TRANSLATION_SERVICES:
            return
        name = 'weblate.machinery.dummy.DummyTranslation'
        service = load_class(name, 'TEST')()
        MACHINE_TRANSLATION_SERVICES[service.mtid] = service

    def test_get_detail(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-detail', kwargs={
                'checksum': unit.checksum,
                'component': unit.translation.component.slug,
                'project': unit.translation.component.project.slug,
            }),
        )
        self.assertContains(response, 'Czech')

    def test_translate(self):
        self.ensure_dummy_mt()
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-translate', kwargs={'unit_id': unit.id}),
            {'service': 'dummy'}
        )
        self.assertContains(response, 'Ahoj')
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(
            data['translations'],
            [
                {
                    'quality': 100,
                    'service': 'Dummy',
                    'text': 'Nazdar světe!',
                    'source': 'Hello, world!\n',
                },
                {
                    'quality': 100,
                    'service': 'Dummy',
                    'text': 'Ahoj světe!',
                    'source': 'Hello, world!\n',
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
        self.assertContains(response, 'href="/changes/?')

    def test_get_unit_translations(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('js-unit-translations', kwargs={'unit_id': unit.id}),
        )
        self.assertContains(response, 'href="/translate/')

    def test_mt_services(self):
        self.ensure_dummy_mt()
        response = self.client.get(reverse('js-mt-services'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        # Check we have dummy service listed
        self.assertIn('dummy', data)
