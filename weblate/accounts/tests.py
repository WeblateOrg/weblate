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

"""
Tests for user handling.
"""

import tempfile
from unittest import TestCase as UnitTestCase
from django.test import TestCase
from unittest import SkipTest
from django.core.urlresolvers import reverse
from django.contrib.auth.models import AnonymousUser, User, Group
from django.contrib.sites.models import Site
from django.core import mail
from django.test.utils import override_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpRequest, HttpResponseRedirect

from weblate.accounts.models import (
    Profile,
    notify_merge_failure,
    notify_new_string,
    notify_new_suggestion,
    notify_new_comment,
    notify_new_translation,
    notify_new_contributor,
    notify_new_language,
)
from weblate.accounts.captcha import (
    hash_question, unhash_question, MathCaptcha
)
from weblate.accounts import avatar
from weblate.accounts.middleware import RequireLoginMiddleware
from weblate.accounts.models import VerifiedEmail

from weblate.trans.tests.test_views import ViewTestCase, RegistrationTestMixin
from weblate.trans.tests.utils import get_test_file
from weblate.trans.tests import OverrideSettings
from weblate.trans.models.unitdata import Suggestion, Comment
from weblate.lang.models import Language

REGISTRATION_DATA = {
    'username': 'username',
    'email': 'noreply@weblate.org',
    'first_name': 'First Last',
    'captcha_id': '00',
    'captcha': '9999'
}


class RegistrationTest(TestCase, RegistrationTestMixin):
    clear_cookie = False

    def assert_registration(self, match=None):
        url = self.assert_registration_mailbox(match)

        if self.clear_cookie:
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

        # Delete session ID from cookies
        del self.client.cookies['sessionid']

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


class NoCookieRegistrationTest(RegistrationTest):
    clear_cookie = True


class CommandTest(TestCase):
    '''
    Tests for management commands.
    '''
    def test_createadmin(self):
        call_command('createadmin')
        user = User.objects.get(username='admin')
        self.assertEqual(user.first_name, 'Weblate Admin')
        self.assertEqual(user.last_name, '')
        self.assertFalse(user.check_password('admin'))

    def test_createadmin_password(self):
        call_command('createadmin', password='admin')
        user = User.objects.get(username='admin')
        self.assertEqual(user.first_name, 'Weblate Admin')
        self.assertEqual(user.last_name, '')
        self.assertTrue(user.check_password('admin'))

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

    def test_importdjangousers(self):
        # First import
        call_command('importusers', get_test_file('users-django.json'))
        self.assertEqual(User.objects.count(), 2)

    def test_userdata(self):
        # Create test user
        user = User.objects.create_user('testuser', 'test@example.com', 'x')
        profile = Profile.objects.create(user=user)
        profile.translated = 1000
        profile.save()

        with tempfile.NamedTemporaryFile() as output:
            call_command('dumpuserdata', output.name)
            call_command('importuserdata', output.name)

        profile = Profile.objects.get(user__username='testuser')
        self.assertEqual(profile.translated, 2000)

    def test_changesite(self):
        call_command('changesite', get_name=True)
        self.assertNotEqual(Site.objects.get(pk=1).domain, 'test.weblate.org')
        call_command('changesite', set_name='test.weblate.org')
        self.assertEqual(Site.objects.get(pk=1).domain, 'test.weblate.org')

    def test_changesite_new(self):
        self.assertRaises(
            CommandError,
            call_command,
            'changesite', get_name=True, site_id=2
        )
        call_command('changesite', set_name='test.weblate.org', site_id=2)
        self.assertEqual(Site.objects.get(pk=2).domain, 'test.weblate.org')


class ViewTest(TestCase):
    '''
    Test for views.
    '''

    def get_user(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        user.first_name = 'First Second'
        user.email = 'noreply@weblate.org'
        user.save()
        Profile.objects.get_or_create(user=user)
        return user

    def test_contact(self):
        '''
        Test for contact form.
        '''
        # Basic get
        response = self.client.get(reverse('contact'))
        self.assertContains(response, 'id="id_message"')

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

    @OverrideSettings(OFFER_HOSTING=False)
    def test_hosting_disabled(self):
        '''
        Test for hosting form with disabled hosting
        '''
        self.get_user()
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(reverse('hosting'))
        self.assertRedirects(response, reverse('home'))

    @OverrideSettings(OFFER_HOSTING=True)
    def test_hosting(self):
        '''
        Test for hosting form with enabled hosting.
        '''
        self.get_user()
        self.client.login(username='testuser', password='testpassword')
        response = self.client.get(reverse('hosting'))
        self.assertContains(response, 'id="id_message"')

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
                'message': 'Hi\n\nI want to use it!',
            }
        )
        self.assertRedirects(response, reverse('home'))

        # Verify message
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Hosting request for HOST'
        )
        self.assertIn(
            'testuser',
            mail.outbox[0].body,
        )

    def test_contact_subject(self):
        # With set subject
        response = self.client.get(
            reverse('contact'),
            {'subject': 'Weblate test message'}
        )
        self.assertContains(response, 'Weblate test message')

    def test_contact_user(self):
        self.get_user()
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
        user = self.get_user()

        # Login as user
        self.client.login(username='testuser', password='testpassword')

        # Get public profile
        response = self.client.get(
            reverse('user_page', kwargs={'user': user.username})
        )
        self.assertContains(response, '="/activity/')

    def test_login(self):
        self.get_user()

        # Login
        response = self.client.post(
            reverse('login'),
            {'username': 'testuser', 'password': 'testpassword'}
        )
        self.assertRedirects(response, reverse('home'))

        # Login redirect
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('profile'))

        # Logout
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('home'))

    def test_password(self):
        # Create user
        self.get_user()
        # Login
        self.client.login(username='testuser', password='testpassword')
        # Change without data
        response = self.client.post(
            reverse('password')
        )
        self.assertContains(response, 'This field is required.')
        response = self.client.get(
            reverse('password'),
        )
        self.assertContains(response, 'Current password')
        # Change with wrong password
        response = self.client.post(
            reverse('password'),
            {
                'password': '123456',
                'password1': '123456',
                'password2': '123456'
            }
        )
        self.assertContains(response, 'You have entered an invalid password.')
        # Change
        response = self.client.post(
            reverse('password'),
            {
                'password': 'testpassword',
                'password1': '123456',
                'password2': '123456'
            }
        )

        self.assertRedirects(response, reverse('profile'))
        self.assertTrue(
            User.objects.get(username='testuser').check_password('123456')
        )


class ProfileTest(ViewTestCase):
    def test_profile(self):
        # Get profile page
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'action="/accounts/profile/"')

        # Save profile
        response = self.client.post(
            reverse('profile'),
            {
                'language': 'cs',
                'languages': Language.objects.get(code='cs').id,
                'secondary_languages': Language.objects.get(code='cs').id,
                'first_name': 'First Last',
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
        user = User.objects.create_user(
            username='seconduser',
            password='secondpassword'
        )
        Profile.objects.create(user=user)
        return user

    def test_notify_merge_failure(self):
        notify_merge_failure(
            self.subproject,
            'Failed merge',
            'Error\nstatus'
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Merge failure in Test/Test'
        )

        # Add project owner
        self.subproject.project.owners.add(self.second_user())
        notify_merge_failure(
            self.subproject,
            'Failed merge',
            'Error\nstatus'
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 5)

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
        second_user = self.second_user()
        notify_new_language(
            self.subproject,
            Language.objects.filter(code='de'),
            second_user
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New language request in Test/Test'
        )

        # Add project owner
        self.subproject.project.owners.add(second_user)
        notify_new_language(
            self.subproject,
            Language.objects.filter(code='de'),
            second_user,
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 5)

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


class CaptchaTest(UnitTestCase):
    def test_decode(self):
        question = '1 + 1'
        timestamp = 1000
        hashed = hash_question(question, timestamp)
        self.assertEqual(
            (question, timestamp),
            unhash_question(hashed)
        )

    def test_tamper(self):
        hashed = hash_question('', 0) + '00'
        self.assertRaises(
            ValueError,
            unhash_question,
            hashed
        )

    def test_invalid(self):
        self.assertRaises(
            ValueError,
            unhash_question,
            ''
        )

    def test_object(self):
        captcha = MathCaptcha('1 * 2')
        self.assertFalse(
            captcha.validate(1)
        )
        self.assertTrue(
            captcha.validate(2)
        )
        restored = MathCaptcha.from_hash(captcha.hashed)
        self.assertEqual(
            captcha.question,
            restored.question
        )
        self.assertRaises(
            ValueError,
            MathCaptcha.from_hash,
            captcha.hashed[:40]
        )

    def test_generate(self):
        '''
        Test generating of captcha for every operator.
        '''
        captcha = MathCaptcha()
        for operator in MathCaptcha.operators:
            captcha.operators = (operator,)
            self.assertIn(operator, captcha.generate_question())


class MiddlewareTest(TestCase):
    def view_method(self):
        return 'VIEW'

    def test_disabled(self):
        middleware = RequireLoginMiddleware()
        request = HttpRequest()
        self.assertIsNone(
            middleware.process_view(request, self.view_method, (), {})
        )

    @override_settings(LOGIN_REQUIRED_URLS=(r'/project/(.*)$',))
    def test_protect_project(self):
        middleware = RequireLoginMiddleware()
        request = HttpRequest()
        request.user = User()
        request.META['SERVER_NAME'] = 'server'
        request.META['SERVER_PORT'] = '80'
        # No protection for not protected path
        self.assertIsNone(
            middleware.process_view(request, self.view_method, (), {})
        )
        request.path = '/project/foo/'
        # No protection for protected path and logged in user
        self.assertIsNone(
            middleware.process_view(request, self.view_method, (), {})
        )
        # Protection for protected path and not logged in user
        request.user = AnonymousUser()
        self.assertIsInstance(
            middleware.process_view(request, self.view_method, (), {}),
            HttpResponseRedirect
        )
        # No protection for login and not logged in user
        request.path = '/accounts/login/'
        self.assertIsNone(
            middleware.process_view(request, self.view_method, (), {})
        )


class AvatarTest(ViewTestCase):
    def setUp(self):
        super(AvatarTest, self).setUp()
        self.user.email = 'test@example.com'
        self.user.save()

    def assert_url(self):
        url = avatar.avatar_for_email(self.user.email)
        self.assertEqual(
            'https://seccdn.libravatar.org/avatar/'
            '55502f40dc8b7c769880b10874abc9d0',
            url.split('?')[0]
        )

    def test_avatar_for_email_own(self):
        backup = avatar.HAS_LIBRAVATAR
        try:
            avatar.HAS_LIBRAVATAR = False
            self.assert_url()
        finally:
            avatar.HAS_LIBRAVATAR = backup

    def test_avatar_for_email_libravatar(self):
        if not avatar.HAS_LIBRAVATAR:
            raise SkipTest('Libravatar not installed')
        self.assert_url()

    def test_avatar(self):
        # Real user
        response = self.client.get(
            reverse(
                'user_avatar',
                kwargs={'user': self.user.username, 'size': 32}
            )
        )
        self.assertPNG(response)
        # Test caching
        response = self.client.get(
            reverse(
                'user_avatar',
                kwargs={'user': self.user.username, 'size': 32}
            )
        )
        self.assertPNG(response)

    def test_anonymous_avatar(self):
        anonymous = User.objects.get(username='anonymous')
        # Anonymous user
        response = self.client.get(
            reverse(
                'user_avatar',
                kwargs={'user': anonymous.username, 'size': 32}
            )
        )
        self.assertPNG(response)


class RemoveAcccountTest(ViewTestCase):
    def test_removal(self):
        response = self.client.post(
            reverse('remove')
        )
        self.assertRedirects(response, reverse('home'))
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
