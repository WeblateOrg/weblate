# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for user handling.
"""

import json

import httpretty
from six.moves.urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings

import social.apps.django_app.utils

from weblate.accounts.models import VerifiedEmail
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests import OverrideSettings

REGISTRATION_DATA = {
    'username': 'username',
    'email': 'noreply-weblate@example.org',
    'first_name': 'First Last',
    'captcha_id': '00',
    'captcha': '9999'
}

GH_BACKENDS = (
    'weblate.accounts.auth.EmailAuth',
    'social.backends.github.GithubOAuth2',
    'weblate.accounts.auth.WeblateUserBackend',
)


class RegistrationTest(TestCase, RegistrationTestMixin):
    clear_cookie = False

    def assert_registration(self, match=None):
        url = self.assert_registration_mailbox(match)

        if self.clear_cookie and 'sessionid' in self.client.cookies:
            del self.client.cookies['sessionid']

        # Confirm account
        response = self.client.get(url, follow=True)
        self.assertRedirects(
            response,
            reverse('password')
        )

    @OverrideSettings(REGISTRATION_CAPTCHA=True)
    def test_register_captcha(self):
        # Enable captcha

        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA
        )
        self.assertContains(
            response,
            'Please check your math and try again.'
        )

    @OverrideSettings(REGISTRATION_OPEN=False)
    def test_register_closed(self):
        # Disable registration
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA
        )
        self.assertContains(
            response,
            'Sorry, but registrations on this site are disabled.'
        )

    @OverrideSettings(REGISTRATION_OPEN=True)
    @OverrideSettings(REGISTRATION_CAPTCHA=False)
    def test_register(self):
        # Disable captcha
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA
        )
        # Check we did succeed
        self.assertRedirects(response, reverse('email-sent'))

        # Confirm account
        self.assert_registration()

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
        self.assertContains(response, 'First Last')

        user = User.objects.get(username='username')
        # Verify user is active
        self.assertTrue(user.is_active)
        # Verify stored first/last name
        self.assertEqual(user.first_name, 'First Last')

    @OverrideSettings(REGISTRATION_OPEN=True)
    @OverrideSettings(REGISTRATION_CAPTCHA=False)
    def test_double_register(self):
        """Test double registration from single browser"""

        # First registration
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA
        )
        first_url = self.assert_registration_mailbox()
        mail.outbox.pop()

        # Second registration
        data = REGISTRATION_DATA.copy()
        data['email'] = 'noreply@example.net'
        data['username'] = 'second'
        response = self.client.post(
            reverse('register'),
            data,
        )
        second_url = self.assert_registration_mailbox()
        mail.outbox.pop()

        # Confirm first account
        response = self.client.get(first_url, follow=True)
        self.assertRedirects(
            response,
            reverse('password')
        )
        self.client.get(reverse('logout'))

        # Confirm second account
        response = self.client.get(second_url, follow=True)
        self.assertRedirects(
            response,
            reverse('password')
        )

    @OverrideSettings(REGISTRATION_OPEN=True)
    @OverrideSettings(REGISTRATION_CAPTCHA=False)
    def test_register_missing(self):
        # Disable captcha
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA
        )
        # Check we did succeed
        self.assertRedirects(response, reverse('email-sent'))

        # Confirm account
        url = self.assert_registration_mailbox()

        # Remove session ID from URL
        url = url.split('&id=')[0]

        # Confirm account
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse('login'))
        self.assertContains(response, 'Failed to verify your registration')

    def test_reset(self):
        '''
        Test for password reset.
        '''
        User.objects.create_user('testuser', 'test@example.com', 'x')

        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'test@example.com'
            }
        )
        self.assertRedirects(response, reverse('email-sent'))

        self.assert_registration('[Weblate] Password reset on Weblate')

    def test_reset_nonexisting(self):
        '''
        Test for password reset.
        '''
        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'test@example.com'
            }
        )
        self.assertRedirects(response, reverse('email-sent'))
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_twice(self):
        '''
        Test for password reset.
        '''
        User.objects.create_user('testuser', 'test@example.com', 'x')
        User.objects.create_user('testuser2', 'test2@example.com', 'x')

        response = self.client.post(
            reverse('password_reset'),
            {'email': 'test@example.com'}
        )
        self.assertRedirects(response, reverse('email-sent'))
        self.assert_registration('[Weblate] Password reset on Weblate')
        sent_mail = mail.outbox.pop()
        self.assertEqual(['test@example.com'], sent_mail.to)

        response = self.client.post(
            reverse('password_reset'),
            {'email': 'test2@example.com'}
        )
        self.assertRedirects(response, reverse('email-sent'))
        self.assert_registration('[Weblate] Password reset on Weblate')
        sent_mail = mail.outbox.pop()
        self.assertEqual(['test2@example.com'], sent_mail.to)

    def test_wrong_username(self):
        data = REGISTRATION_DATA.copy()
        data['username'] = ''
        response = self.client.post(
            reverse('register'),
            data
        )
        self.assertContains(
            response,
            'This field is required.',
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
            'Enter a valid email address.'
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

    def test_add_mail(self):
        # Create user
        self.test_register()
        mail.outbox.pop()

        # Check adding email page
        response = self.client.get(
            reverse('email_login')
        )
        self.assertContains(response, 'Register email')

        # Try invalid address first
        response = self.client.post(
            reverse('email_login'),
            {'email': 'invalid'},
        )
        self.assertContains(response, 'has-error')

        # Add email account
        response = self.client.post(
            reverse('email_login'),
            {'email': 'second@example.net'},
            follow=True,
        )
        self.assertRedirects(response, reverse('email-sent'))

        # Verify confirmation mail
        url = self.assert_registration_mailbox()
        response = self.client.get(url, follow=True)
        self.assertRedirects(
            response, '{0}#auth'.format(reverse('profile'))
        )

        # Check database models
        user = User.objects.get(username='username')
        self.assertEqual(
            VerifiedEmail.objects.filter(social__user=user).count(), 2
        )
        self.assertTrue(
            VerifiedEmail.objects.filter(
                social__user=user, email='second@example.net'
            ).exists()
        )

    @httpretty.activate
    @override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_github(self):
        """Test GitHub integration"""
        try:
            # psa creates copy of settings...
            orig_backends = social.apps.django_app.utils.BACKENDS
            social.apps.django_app.utils.BACKENDS = GH_BACKENDS

            httpretty.register_uri(
                httpretty.POST,
                'https://github.com/login/oauth/access_token',
                body=json.dumps({
                    'access_token': '123',
                    'token_type': 'bearer',
                })
            )
            httpretty.register_uri(
                httpretty.GET,
                'https://api.github.com/user',
                body=json.dumps({
                    'email': 'foo@example.net',
                    'login': 'weblate',
                    'id': 1,
                    'name': 'Weblate',
                }),
            )
            httpretty.register_uri(
                httpretty.GET,
                'https://api.github.com/user/emails',
                body=json.dumps([
                    {
                        'email': 'noreply2@example.org',
                        'verified': False,
                        'primary': False,
                    }, {
                        'email': 'noreply-weblate@example.org',
                        'verified': True,
                        'primary': True
                    }
                ])
            )
            response = self.client.get(
                reverse('social:begin', args=('github',))
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(
                response['Location'].startswith(
                    'https://github.com/login/oauth/authorize'
                )
            )
            query = parse_qs(urlparse(response['Location']).query)
            return_query = parse_qs(urlparse(query['redirect_uri'][0]).query)
            response = self.client.get(
                reverse('social:complete', args=('github',)),
                {
                    'state': query['state'][0],
                    'redirect_state': return_query['redirect_state'][0],
                    'code': 'XXX'
                },
                follow=True
            )
            user = User.objects.get(username='weblate')
            self.assertEqual(user.first_name, 'Weblate')
            self.assertEqual(user.email, 'noreply-weblate@example.org')
        finally:
            social.apps.django_app.utils.BACKENDS = orig_backends


class NoCookieRegistrationTest(RegistrationTest):
    clear_cookie = True
