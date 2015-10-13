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


from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.views.reports import generate_credits
from django.core.urlresolvers import reverse
from django.utils import timezone
from datetime import timedelta
import json


class ReportsTest(ViewTestCase):
    def setUp(self):
        super(ReportsTest, self).setUp()
        self.user.is_superuser = True
        self.user.save()

    def add_change(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )

    def test_credits_empty(self):
        data = generate_credits(
            self.subproject,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1)
        )
        self.assertEqual(data, [])

    def test_credits_one(self):
        self.add_change()
        data = generate_credits(
            self.subproject,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1)
        )
        self.assertEqual(
            data,
            [{'Czech': [('noreply@weblate.org', 'Weblate Test')]}]
        )

    def test_credits_more(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete2!\n'
        )
        self.test_credits_one()

    def test_credits_view_json(self):
        self.add_change()
        response = self.client.post(
            reverse('credits', kwargs=self.kw_subproject),
            {
                'style': 'json',
                'start_date': '2000-01-01',
                'end_date': '2100-01-01'
            },
        )
        data = json.loads(response.content)
        self.assertEqual(
            data,
            [{'Czech': [['noreply@weblate.org', 'Weblate Test']]}]
        )

    def test_credits_view_rst(self):
        self.add_change()
        response = self.client.post(
            reverse('credits', kwargs=self.kw_subproject),
            {
                'style': 'rst',
                'start_date': '2000-01-01',
                'end_date': '2100-01-01'
            },
        )
        self.assertEqual(
            response.content,
            '* Czech\n\n    * Weblate Test <noreply@weblate.org>\n'
        )
