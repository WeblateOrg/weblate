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
from accounts.models import (
    Profile,
    notify_merge_failure,
    notify_new_string,
    notify_new_suggestion,
    notify_new_comment,
    notify_new_translation,
    notify_new_contributor,
    notify_new_language,
)

from trans.tests.views import ViewTestCase
from trans.tests.util import get_test_file
from trans.models.unitdata import Suggestion, Comment
from lang.models import Language
from weblate import appsettings

REGISTRATION_DATA = {
    'username': 'username',
    'email': 'noreply@weblate.org',
    'first_name': 'First',
    'last_name': 'Last',
}


class RegistrationTest(TestCase):
    def assertRegistration(self):
        # Check registration mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Your registration on Weblate'
        )

        # Get confirmation URL from mail
        line = ''
        for line in mail.outbox[0].body.splitlines():
            if line.startswith('http://example.com'):
                break

        # Confirm account
        response = self.client.get(line[18:], follow=True)
        self.assertRedirects(
            response,
            reverse('password')
        )

    def test_register(self):
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA
        )
        # Check we did succeed
        self.assertRedirects(response, reverse('email-sent'))

        # Confirm account
        self.assertRegistration()

        # Set password
        response = self.client.post(
            reverse('password'),
            {
                'password1': 'password',
                'password2': 'password',
            }
        )
        self.assertRedirects(response, reverse('profile'))

        # Check we can access home (was redirected to password change)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Logged in as')

        user = User.objects.get(username='username')
        # Verify user is active
        self.assertTrue(user.is_active)
        # Verify stored first/last name
        self.assertEqual(user.first_name, 'First')
        self.assertEqual(user.last_name, 'Last')

    def test_reset(self):
        '''
        Test for password reset.
        '''
        User.objects.create_user('testuser', 'test@example.com', 'x')

        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'test@example.com'
            }
        )
        self.assertRedirects(response, reverse('email-sent'))

        self.assertRegistration()

    def test_wrong_username(self):
        data = REGISTRATION_DATA.copy()
        data['username'] = 'u'
        response = self.client.post(
            reverse('register'),
            data
        )
        self.assertContains(
            response,
            'Ensure this value has at least 5 characters (it has 1).'
        )

    def test_wrong_mail(self):
        data = REGISTRATION_DATA.copy()
        data['email'] = 'x'
        response = self.client.post(
            reverse('register'),
            data
        )
        self.assertContains(
            response,
            'Enter'
        )
        # Error message has changed in Django 1.5
        self.assertTrue(
            'Enter a valid e-mail address.' in response.content
            or 'Enter a valid email address.' in response.content
        )

    def test_spam(self):
        data = REGISTRATION_DATA.copy()
        data['content'] = 'x'
        response = self.client.post(
            reverse('register'),
            data
        )
        self.assertContains(
            response,
            'Invalid value'
        )


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

    def test_importusers(self):
        # First import
        call_command('importusers', get_test_file('users.json'))

        # Test that second import does not change anything
        user = User.objects.get(username='weblate')
        user.first_name = 'Weblate test user'
        user.save()
        call_command('importusers', get_test_file('users.json'))
        user2 = User.objects.get(username='weblate')
        self.assertEqual(user.first_name, user2.first_name)


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

    def test_hosting(self):
        '''
        Test for contact form.
        '''
        # Hack to allow sending of mails
        settings.ADMINS = (('Weblate test', 'noreply@weblate.org'), )

        # Disabled hosting
        appsettings.OFFER_HOSTING = False
        response = self.client.get(reverse('hosting'))
        self.assertRedirects(response, reverse('home'))

        # Enabled
        appsettings.OFFER_HOSTING = True
        response = self.client.get(reverse('hosting'))
        self.assertContains(response, 'class="contact-table"')

        # Sending message
        response = self.client.post(
            reverse('hosting'),
            {
                'name': 'Test',
                'email': 'noreply@weblate.org',
                'project': 'HOST',
                'url': 'http://example.net',
                'repo': 'git://github.com/nijel/weblate.git',
                'mask': 'po/*.po',
                'message': 'Hi\n\nThis app looks really cool I want to use it!',
            }
        )
        self.assertRedirects(response, reverse('home'))

        # Verify message
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Hosting request for HOST'
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
        user.first_name = 'First'
        user.last_name = 'Second'
        user.email = 'noreply@weblate.org'
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


class ProfileTest(ViewTestCase):
    def test_profile(self):
        # Get profile page
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'class="tabs preferences"')

        # Save profile
        response = self.client.post(
            reverse('profile'),
            {
                'language': 'cs',
                'languages': Language.objects.get(code='cs').id,
                'secondary_languages': Language.objects.get(code='cs').id,
                'first_name': 'First',
                'last_name': 'Last',
                'email': 'noreply@weblate.org',
                'username': 'testik',
            }
        )
        self.assertRedirects(response, reverse('profile'))


class NotificationTest(ViewTestCase):
    def setUp(self):
        super(NotificationTest, self).setUp()
        self.user.email = 'noreply@weblate.org'
        self.user.save()
        profile = Profile.objects.get(user=self.user)
        profile.subscribe_any_translation = True
        profile.subscribe_new_string = True
        profile.subscribe_new_suggestion = True
        profile.subscribe_new_contributor = True
        profile.subscribe_new_comment = True
        profile.subscribe_new_language = True
        profile.subscribe_merge_failure = True
        profile.subscriptions.add(self.project)
        profile.languages.add(
            Language.objects.get(code='cs')
        )
        profile.save()

    def second_user(self):
        return User.objects.create_user(
            username='seconduser',
            password='secondpassword'
        )

    def test_notify_merge_failure(self):
        notify_merge_failure(
            self.subproject,
            'Failed merge',
            'Error\nstatus'
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Merge failure in Test/Test'
        )

    def test_notify_new_string(self):
        notify_new_string(self.get_translation())

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New string to translate in Test/Test - Czech'
        )

    def test_notify_new_translation(self):
        unit = self.get_unit()
        unit2 = self.get_translation().unit_set.get(
            source='Thank you for using Weblate.'
        )
        notify_new_translation(
            unit,
            unit2,
            self.second_user()
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New translation in Test/Test - Czech'
        )

    def test_notify_new_language(self):
        notify_new_language(
            self.subproject,
            Language.objects.filter(code='de'),
            self.second_user()
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New language request in Test/Test'
        )

    def test_notify_new_contributor(self):
        unit = self.get_unit()
        notify_new_contributor(
            unit,
            self.second_user()
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New contributor in Test/Test - Czech'
        )

    def test_notify_new_suggestion(self):
        unit = self.get_unit()
        notify_new_suggestion(
            unit,
            Suggestion.objects.create(
                contentsum=unit.contentsum,
                project=unit.translation.subproject.project,
                language=unit.translation.language,
                target='Foo'
            ),
            self.second_user()
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New suggestion in Test/Test - Czech'
        )

    def test_notify_new_comment(self):
        unit = self.get_unit()
        notify_new_comment(
            unit,
            Comment.objects.create(
                contentsum=unit.contentsum,
                project=unit.translation.subproject.project,
                language=unit.translation.language,
                comment='Foo'
            ),
            self.second_user(),
            ''
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New comment in Test/Test'
        )

    def test_notify_new_comment_report(self):
        unit = self.get_unit()
        notify_new_comment(
            unit,
            Comment.objects.create(
                contentsum=unit.contentsum,
                project=unit.translation.subproject.project,
                language=None,
                comment='Foo'
            ),
            self.second_user(),
            'noreply@weblate.org'
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New comment in Test/Test'
        )
        self.assertEqual(
            mail.outbox[1].subject,
            '[Weblate] New comment in Test/Test'
        )
