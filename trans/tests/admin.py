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

from trans.tests.views import ViewTestCase
from django.core.urlresolvers import reverse


class AdminTest(ViewTestCase):
    '''
    Tests for customized admin interface.
    '''
    def setUp(self):
        super(AdminTest, self).setUp()
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

    def test_index(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'SSH')

    def test_ssh(self):
        response = self.client.get(reverse('admin-ssh'))
        self.assertContains(response, 'SSH keys')

    def test_performace(self):
        response = self.client.get(reverse('admin-performance'))
        self.assertContains(response, 'Django caching')

    def test_report(self):
        response = self.client.get(reverse('admin-report'))
        self.assertContains(response, 'On branch master')
