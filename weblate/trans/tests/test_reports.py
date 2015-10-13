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

    def add_change(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )

    def test_credits_empty(self):
        credits = generate_credits(
            self.subproject,
            timezone.now() - timedelta(days=1)
        )
        self.assertEqual(credits, [])

    def test_credits_one(self):
        self.add_change()
        credits = generate_credits(
            self.subproject,
            timezone.now() - timedelta(days=1)
        )
        self.assertEqual(
            credits,
            [{'Czech': [('noreply@weblate.org', 'Weblate Test')]}]
        )

    def test_credits_more(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete2!\n'
        )
        self.test_credits_one()

    def test_credits_view_json(self):
        self.add_change()
        response = self.client.post(
            reverse('credits', kwargs=self.kw_subproject),
            {'style': 'json', 'start_date': '2000-01-01'},
        )
        credits = json.loads(response.content)
        self.assertEqual(
            credits,
            [{'Czech': [['noreply@weblate.org', 'Weblate Test']]}]
        )
