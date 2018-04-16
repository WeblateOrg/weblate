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
from django.urls import reverse

from weblate.screenshots.models import Screenshot
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
import weblate.screenshots.views

TEST_SCREENSHOT = get_test_file('screenshot.png')


class ViewTest(FixtureTestCase):
    def test_list_empty(self):
        response = self.client.get(
            reverse('screenshots', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Screenshots')

    def do_upload(self, **kwargs):
        with open(TEST_SCREENSHOT, 'rb') as handle:
            data = {'image': handle, 'name': 'Obrazek'}
            data.update(kwargs)
            return self.client.post(
                reverse('screenshots', kwargs=self.kw_component),
                data,
                follow=True
            )

    def test_upload_denied(self):
        response = self.do_upload()
        self.assertEqual(response.status_code, 403)

    def test_upload(self):
        self.make_manager()
        response = self.do_upload()
        self.assertContains(response, 'Obrazek')
        self.assertEqual(Screenshot.objects.count(), 1)

    def test_upload_fail(self):
        self.make_manager()
        response = self.do_upload(name='')
        self.assertContains(response, 'Failed to upload screenshot')
        response = self.do_upload(image='')
        self.assertContains(response, 'Failed to upload screenshot')

    def test_upload_source(self):
        self.make_manager()
        source = self.component.source_set.all()[0]
        response = self.do_upload(source=source.pk)
        self.assertContains(response, 'Obrazek')
        self.assertEqual(Screenshot.objects.count(), 1)
        screenshot = Screenshot.objects.all()[0]
        self.assertEqual(screenshot.name, 'Obrazek')
        self.assertEqual(screenshot.sources.count(), 1)

    def test_upload_source_invalid(self):
        self.make_manager()
        response = self.do_upload(source='wrong')
        self.assertContains(response, 'Obrazek')

    def test_edit(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]
        response = self.client.post(
            screenshot.get_absolute_url(),
            {'name': 'Picture'},
            follow=True
        )
        self.assertContains(response, 'Picture')
        self.assertEqual(Screenshot.objects.all()[0].name, 'Picture')

    def test_delete(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]
        self.client.post(
            reverse('screenshot-delete', kwargs={'pk': screenshot.pk})
        )
        self.assertEqual(Screenshot.objects.count(), 0)

    def test_source_manipulations(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]

        # Search for string
        response = self.client.post(
            reverse('screenshot-js-search', kwargs={'pk': screenshot.pk}),
            {'q': 'hello'}
        )
        data = response.json()
        self.assertEqual(data['responseCode'], 200)
        self.assertEqual(len(data['results']), 1)

        source_pk = data['results'][0]['pk']

        # Add found string
        response = self.client.post(
            reverse('screenshot-js-add', kwargs={'pk': screenshot.pk}),
            {'source': source_pk},
        )
        data = response.json()
        self.assertEqual(data['responseCode'], 200)
        self.assertEqual(data['status'], True)
        self.assertEqual(screenshot.sources.count(), 1)

        # Updated listing
        response = self.client.get(
            reverse('screenshot-js-get', kwargs={'pk': screenshot.pk}),
        )
        self.assertContains(response, 'Hello')

        # Remove added string
        self.client.post(
            reverse('screenshot-remove-source', kwargs={'pk': screenshot.pk}),
            {'source': source_pk},
        )
        self.assertEqual(screenshot.sources.count(), 0)

    def test_ocr(self):
        self.make_manager()
        self.do_upload()
        screenshot = Screenshot.objects.all()[0]

        # Search for string
        response = self.client.post(
            reverse('screenshot-js-ocr', kwargs={'pk': screenshot.pk})
        )
        data = response.json()

        if not weblate.screenshots.views.HAS_OCR:
            self.assertEqual(data['responseCode'], 500)
            return

        self.assertEqual(data['responseCode'], 200)
        # We should find at least one string
        self.assertGreaterEqual(len(data['results']), 1)
