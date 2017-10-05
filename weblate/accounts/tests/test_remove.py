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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test for account removal."""

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase

from weblate.trans.tests.test_views import ViewTestCase, RegistrationTestMixin


class AccountRemovalTest(ViewTestCase, RegistrationTestMixin):
    def test_page(self):
        response = self.client.get(reverse('remove'))
        self.assertContains(
            response,
            'Removal of the account deletes all your private data'
        )

    def test_removal(self):
        response = self.client.post(
            reverse('remove'),
            {'password': 'testpassword'},
            follow=True
        )
        self.assertContains(
            response,
            'Your account has been removed.',
        )
        self.assertFalse(
            User.objects.filter(username='testuser').exists()
        )

    def test_removal_failed(self):
        response = self.client.post(
            reverse('remove'),
            {'password': 'invalidpassword'},
            follow=True
        )
        self.assertContains(
            response,
            'You have entered an invalid password.',
        )
        self.assertTrue(
            User.objects.filter(username='testuser').exists()
        )

    def test_removal_nopass(self):
        # Set unusuable password for test user.
        self.user.set_unusable_password()
        self.user.save()
        # Need to force login as user has no password now.
        # In the app he would login by third party auth.
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('remove'),
            {'password': ''},
            follow=True
        )
        self.assertContains(
            response,
            'Your account has been removed.',
        )
        self.assertFalse(
            User.objects.filter(username='testuser').exists()
        )

    def test_removal_change(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should have some change to commit
        self.assertTrue(self.subproject.repo_needs_commit())
        # Remove account
        self.test_removal()
        # Changes should be committed
        self.assertFalse(self.subproject.repo_needs_commit())
