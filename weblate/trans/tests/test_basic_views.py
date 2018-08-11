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

"""
Tests for data exports.
"""

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class BasicViewTest(FixtureTestCase):
    def test_about(self):
        response = self.client.get(
            reverse('about')
        )
        self.assertContains(response, 'translate-toolkit')

    def test_keys(self):
        response = self.client.get(
            reverse('keys')
        )
        self.assertContains(response, 'SSH')

    def test_stats(self):
        response = self.client.get(
            reverse('stats')
        )
        self.assertContains(response, 'Weblate statistics')

    def test_healthz(self):
        response = self.client.get(
            reverse('healthz')
        )
        self.assertContains(response, 'ok')
