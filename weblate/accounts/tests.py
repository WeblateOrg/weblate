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
Tests for user handling.
"""

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group
from django.core import mail
from django.core.management import call_command


class RegistrationTest(TestCase):
    def test_register(self):
        response = self.client.post(
            reverse('weblate_register'),
            {
                'username': 'username',
                'email': 'noreply@weblate.org',
                'password1': 'password',
                'password2': 'password',
                'first_name': 'First',
                'last_name': 'Last',
            }
        )
        # Check we did succeed
        self.assertRedirects(response, reverse('registration_complete'))

        # Check registration mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'Your registration on Weblate'
        )

        # Get confirmation URL from mail
        line = ''
        for line in mail.outbox[0].body.splitlines():
            if line.startswith('http://example.com'):
                break

        # Confirm account
        response = self.client.get(line[18:])
        self.assertRedirects(
            response,
            reverse('registration_activation_complete')
        )

        user = User.objects.get(username='username')
        # Verify user is active
        self.assertTrue(user.is_active)
        # Verify stored first/last name
        self.assertEqual(user.first_name, 'First')
        self.assertEqual(user.last_name, 'Last')


class CommandTest(TestCase):
    '''
    Tests for management commands.
    '''
    def test_createadmin(self):
        call_command('createadmin')
        user = User.objects.get(username='admin')
        self.asserEqual(user.first_name, 'Weblate')
        self.asserEqual(user.last_name, 'Admin')

    def test_setupgroups(self):
        call_command('setupgroups')
        group = Group.objects.get(name='Users')
