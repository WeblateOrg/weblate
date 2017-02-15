# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from django.core.urlresolvers import reverse

from weblate.screenshots.models import Screenshot
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file

TEST_SCREENSHOT = get_test_file('screenshot.png')


class ViewTest(ViewTestCase):
    def test_list_empty(self):
        response = self.client.get(
            reverse('screenshots', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Screenshots')

    def do_upload(self):
        with open(TEST_SCREENSHOT, 'rb') as handle:
            return self.client.post(
                reverse('screenshots', kwargs=self.kw_subproject),
                {'image': handle, 'name': 'Obrazek'},
                follow=True
            )

    def test_upload_denied(self):
        response = self.do_upload()
        self.assertEqual(response.status_code, 403)

    def test_upload(self):
        self.make_manager()
        response = self.do_upload()
        self.assertContains(response, 'Obrazek')
        self.assertEqual(
            Screenshot.objects.count(), 1
        )

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
        self.assertEqual(
            Screenshot.objects.all()[0].name, 'Picture'
        )
