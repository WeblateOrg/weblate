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
from django.conf import settings
from django.core.management import call_command
from accounts.models import Profile


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
        self.assertEqual(user.first_name, 'Weblate')
        self.assertEqual(user.last_name, 'Admin')

    def test_setupgroups(self):
        call_command('setupgroups')
        group = Group.objects.get(name='Users')
        self.assertTrue(
            group.permissions.filter(
                codename='save_translation'
            ).exists()
        )
        call_command('setupgroups', move=True)


class ViewTest(TestCase):
    '''
    Test for views.
    '''
    def test_contact(self):
        '''
        Test for contact form.
        '''
        # Hack to allow sending of mails
        settings.ADMINS = (('Weblate test', 'noreply@weblate.org'), )
        # Basic get
        response = self.client.get(reverse('contact'))
        self.assertContains(response, 'class="contact-table"')

        # Sending message
        response = self.client.post(
            reverse('contact'),
            {
                'name': 'Test',
                'email': 'noreply@weblate.org',
                'subject': 'Message from dark side',
                'message': 'Hi\n\nThis app looks really cool!',
            }
        )
        self.assertRedirects(response, reverse('home'))

        # Verify message
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Message from dark side'
        )

    def test_contact_subject(self):
        # With set subject
        response = self.client.get(
            reverse('contact'),
            {'subject': 'Weblate test message'}
        )
        self.assertContains(response, 'Weblate test message')

    def test_contact_user(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpassword',
        )
        user.first_name='First'
        user.last_name='Second'
        user.email='noreply@weblate.org'
        user.save()
        Profile.objects.get_or_create(user=user)
        # Login
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(
            reverse('contact'),
        )
        self.assertContains(response, 'value="First Second"')
        self.assertContains(response, 'noreply@weblate.org')

    def test_user(self):
        '''
        Test user pages.
        '''
        # Setup user
        user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        Profile.objects.get_or_create(user=user)

        # Login as user
        self.client.login(username='testuser', password='testpassword')

        # Get public profile
        response = self.client.get(
            reverse('user_page', kwargs={'user': user.username})
        )
        self.assertContains(response, 'src="/activity')

        # Get profile page
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'class="tabs preferences"')
