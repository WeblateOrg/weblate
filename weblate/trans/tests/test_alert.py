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

"""Test for automatic translation"""

from django.urls import reverse

from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase


class AlertTest(ViewTestCase):
    def create_component(self):
        return self._create_component(
            'po',
            'po-duplicates/*.dpo',
        )

    def test_duplicates(self):
        self.assertEqual(self.component.alert_set.count(), 2)
        alert = self.component.alert_set.get(name='DuplicateLanguage')
        self.assertEqual(
            alert.details['occurences'][0]['language_code'],
            'cs',
        )
        alert = self.component.alert_set.get(name='DuplicateString')
        self.assertEqual(
            alert.details['occurences'][0]['source'],
            'Thank you for using Weblate.'
        )

    def test_view(self):
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, 'Duplicated translation')
