# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
Tests for changes browsing.
"""

from trans.tests.views import ViewTestCase
from django.core.urlresolvers import reverse


class ChangesTest(ViewTestCase):
    def test_basic(self):
        response = self.client.get(reverse('changes'))
        self.assertContains(response, 'Resource update')

    def test_filter(self):
        response = self.client.get(
            reverse('changes'),
            {'project': 'test'}
        )
        self.assertContains(response, 'Resource update')
        response = self.client.get(
            reverse('changes'),
            {'project': 'test', 'subproject': 'test'}
        )
        self.assertContains(response, 'Resource update')
        response = self.client.get(
            reverse('changes'),
            {'project': 'test', 'subproject': 'test', 'lang': 'cs'}
        )
        self.assertContains(response, 'Resource update')
