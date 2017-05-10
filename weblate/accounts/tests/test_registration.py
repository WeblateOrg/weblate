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

"""Test for user handling."""

import json

import httpretty
from six.moves.urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings

import social_django.utils

from weblate.accounts.models import VerifiedEmail
from weblate.accounts.ratelimit import reset_rate_limit

from weblate.trans.tests.test_views import RegistrationTestMixin

REGISTRATION_DATA = {
    'username': 'username',
    'email': 'noreply-weblate@example.org',
    'first_name': 'First Last',
    'captcha_id': '00',
    'captcha': '9999'
}

GH_BACKENDS = (
    'weblate.accounts.auth.EmailAuth',
    'social_core.backends.github.GithubOAuth2',
    'weblate.accounts.auth.WeblateUserBackend',
)


class RegistrationTest(TestCase, RegistrationTestMixin):
    clear_cookie = False

    def setUp(self):
        super(RegistrationTest, self).setUp()
        reset_rate_limit(address='127.0.0.1')

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
        return url

    @override_settings(REGISTRATION_CAPTCHA=True)
    def test_register_captcha_fail(self):
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA,
            follow=True
        )
        self.assertContains(
            response,
            'Please check your math and try again.'
        )

    @override_settings(REGISTRATION_CAPTCHA=True)
    def test_register_captcha(self):
        """Test registration with captcha enabled."""
        response = self.client.get(
            reverse('register')
        )
        form = response.context['captcha_form']
        data = REGISTRATION_DATA.copy()
        data['captcha_id'] = form.fields['captcha_id'].initial
        data['captcha'] = form.captcha.result
        response = self.client.post(
            reverse('register'),
            data,
            follow=True
        )
        self.assertContains(response, 'Thank you for registering.')

        # Second registration should fail
        response = self.client.post(
            reverse('register'),
            data,
            follow=True
        )
        self.assertNotContains(response, 'Thank you for registering.')

    @override_settings(REGISTRATION_OPEN=False)
    def test_register_closed(self):
        # Disable registration
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA,
            follow=True
        )
        self.assertContains(
            response,
            'Sorry, but registrations on this site are disabled.'
        )

    @override_settings(REGISTRATION_OPEN=True)
    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_register(self):
        # Disable captcha
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA,
            follow=True
        )
        # Check we did succeed
        self.assertContains(response, 'Thank you for registering.')

        # Confirm account
        self.assert_registration()
        mail.outbox.pop()

        # Set password
        response = self.client.post(
            reverse('password'),
            {
                'new_password1': '1pa$$word!',
                'new_password2': '1pa$$word!',
            }
        )
        self.assertRedirects(response, reverse('profile'))
        # Password change notification
        notification = mail.outbox.pop()
        self.assertEqual(
            notification.subject,
            '[Weblate] Activity on your account at Weblate'
        )

        # Check we can access home (was redirected to password change)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'First Last')

        user = User.objects.get(username='username')
        # Verify user is active
        self.assertTrue(user.is_active)
        # Verify stored first/last name
        self.assertEqual(user.first_name, 'First Last')

        # Ensure we've picked up all mails
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_OPEN=True)
    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_double_link(self):
        """Test that verification link works just once."""
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA,
            follow=True
        )
        # Check we did succeed
        self.assertContains(response, 'Thank you for registering.')
        url = self.assert_registration()

        # Clear cookies
        if self.clear_cookie and 'sessionid' in self.client.cookies:
            del self.client.cookies['sessionid']

        response = self.client.get(url, follow=True)
        self.assertContains(
            response,
            'Email couldn&#39;t be validated'
        )

    @override_settings(REGISTRATION_OPEN=True)
    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_double_register_logout(self, logout=True):
        """Test double registration from single browser with logout."""

        # First registration
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA,
            follow=True
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
            follow=True
        )
        second_url = self.assert_registration_mailbox()
        mail.outbox.pop()

        # Confirm first account
        response = self.client.get(first_url, follow=True)
        self.assertTrue(
            User.objects.filter(email='noreply-weblate@example.org').exists()
        )
        self.assertRedirects(
            response,
            reverse('password')
        )
        if logout:
            self.client.post(reverse('logout'))

        # Confirm second account
        response = self.client.get(second_url, follow=True)
        self.assertEqual(
            User.objects.filter(email='noreply@example.net').exists(),
            logout
        )
        self.assertEqual(
            VerifiedEmail.objects.filter(email='noreply@example.net').exists(),
            logout
        )

    def test_double_register(self):
        """Test double registration from single browser without logout."""
        self.test_double_register_logout(False)

    @override_settings(REGISTRATION_OPEN=True)
    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_register_missing(self):
        """Test handling of incomplete registration URL."""
        # Disable captcha
        response = self.client.post(
            reverse('register'),
            REGISTRATION_DATA,
            follow=True
        )
        # Check we did succeed
        self.assertContains(response, 'Thank you for registering.')

        # Confirm account
        url = self.assert_registration_mailbox()

        # Remove partial_token from URL
        url = url.split('?')[0]

        # Confirm account
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse('login'))
        self.assertContains(response, 'Failed to verify your registration')

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset(self):
        """Test for password reset."""
        User.objects.create_user('testuser', 'test@example.com', 'x')

        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'test@example.com'
            },
            follow=True
        )
        self.assertContains(response, 'Thank you for registering.')

        self.assert_registration('[Weblate] Password reset on Weblate')

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_nonexisting(self):
        """Test for password reset of nonexisting email."""
        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'test@example.com'
            },
            follow=True
        )
        self.assertContains(response, 'Thank you for registering.')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_invalid(self):
        """Test for password reset of invalid email."""
        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': '@example.com'
            }
        )
        self.assertContains(
            response,
            'Enter a valid email address.'
        )
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=True)
    def test_reset_captcha(self):
        """Test for password reset of invalid captcha."""
        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'test@example.com',
                'captcha': 9999,
            }
        )
        self.assertContains(
            response,
            'Please check your math and try again.'
        )
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_anonymous(self):
        """Test for password reset of anonymous user."""
        response = self.client.get(
            reverse('password_reset'),
        )
        self.assertContains(response, 'Reset my password')
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'noreply@weblate.org'
            }
        )
        self.assertContains(
            response,
            'No password reset for deleted or anonymous user.'
        )
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_reset_twice(self):
        """Test for password reset."""
        User.objects.create_user('testuser', 'test@example.com', 'x')
        User.objects.create_user('testuser2', 'test2@example.com', 'x')

        response = self.client.post(
            reverse('password_reset'),
            {'email': 'test@example.com'}
        )
        self.assertRedirects(response, reverse('email-sent'))
        self.assert_registration('[Weblate] Password reset on Weblate')
        # Pop notifications (new association + reset)
        sent_mail = mail.outbox.pop()
        sent_mail = mail.outbox.pop()
        self.assertEqual(['test@example.com'], sent_mail.to)
        self.assertEqual(
            sent_mail.subject,
            '[Weblate] Activity on your account at Weblate'
        )
        # Pop password change
        sent_mail = mail.outbox.pop()

        response = self.client.post(
            reverse('password_reset'),
            {'email': 'test2@example.com'}
        )
        self.assertRedirects(response, reverse('email-sent'))
        self.assert_registration('[Weblate] Password reset on Weblate')
        # Pop notifications (new association + reset)
        sent_mail = mail.outbox.pop()
        sent_mail = mail.outbox.pop()
        self.assertEqual(['test2@example.com'], sent_mail.to)
        # Pop password change
        sent_mail = mail.outbox.pop()

    def test_wrong_username(self):
        data = REGISTRATION_DATA.copy()
        data['username'] = ''
        response = self.client.post(
            reverse('register'),
            data,
            follow=True
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
            data,
            follow=True
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
            data,
            follow=True
        )
        self.assertContains(
            response,
            'Invalid value'
        )

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_add_mail(self):
        """Adding mail to existing account."""
        # Create user
        self.test_register()

        # Check adding email page
        response = self.client.post(
            reverse('social:begin', args=('email',)),
            follow=True,
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
        self.assertRedirects(response, reverse('confirm'))

        # Enter wrong password
        response = self.client.post(
            reverse('confirm'),
            {'password': 'invalid'}
        )
        self.assertContains(response, 'You have entered an invalid password.')

        # Correct password
        response = self.client.post(
            reverse('confirm'),
            {'password': '1pa$$word!'},
            follow=True
        )
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

        # Check notification
        notification = mail.outbox.pop()
        self.assertEqual(
            notification.subject,
            '[Weblate] Activity on your account at Weblate'
        )

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_pipeline_redirect(self):
        """Test pipeline redirect using next parameter."""
        # Create user
        self.test_register()

        # Valid next URL
        response = self.client.post(
            reverse('social:begin', args=('email',)),
            {'next': '/#valid'}
        )
        response = self.client.post(
            reverse('email_login'),
            {'email': 'second@example.net'},
            follow=True,
        )
        self.assertRedirects(response, reverse('email-sent'))

        # Verify confirmation mail
        url = self.assert_registration_mailbox()
        # Confirmation
        mail.outbox.pop()
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse('confirm'))
        response = self.client.post(
            reverse('confirm'),
            {'password': '1pa$$word!'},
            follow=True
        )
        self.assertRedirects(response, '/#valid')
        # Activity
        mail.outbox.pop()

        # Invalid next URL
        response = self.client.post(
            reverse('social:begin', args=('email',)),
            {'next': '////example.com'}
        )
        response = self.client.post(
            reverse('email_login'),
            {'email': 'third@example.net'},
            follow=True,
        )
        self.assertRedirects(response, reverse('email-sent'))

        # Verify confirmation mail
        url = self.assert_registration_mailbox()
        response = self.client.get(url, follow=True)
        self.assertRedirects(response, reverse('confirm'))
        response = self.client.post(
            reverse('confirm'),
            {'password': '1pa$$word!'},
            follow=True
        )
        # We should fallback to default URL
        self.assertRedirects(response, '/accounts/profile/#auth')

    @httpretty.activate
    @override_settings(AUTHENTICATION_BACKENDS=GH_BACKENDS)
    def test_github(self):
        """Test GitHub integration"""
        try:
            # psa creates copy of settings...
            orig_backends = social_django.utils.BACKENDS
            social_django.utils.BACKENDS = GH_BACKENDS

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
            response = self.client.post(
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
            social_django.utils.BACKENDS = orig_backends


class NoCookieRegistrationTest(RegistrationTest):
    clear_cookie = True
