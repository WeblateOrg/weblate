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
Tests for user handling.
"""

from django.core import mail
from django.test.utils import override_settings

from weblate.auth.models import User
from weblate.accounts.models import Profile
from weblate.accounts.notifications import (
    notify_merge_failure,
    notify_parse_error,
    notify_new_string,
    notify_new_suggestion,
    notify_new_comment,
    notify_new_translation,
    notify_new_contributor,
    notify_new_language,
    notify_account_activity,
)
from weblate.trans.tests.test_views import (
    FixtureTestCase, RegistrationTestMixin,
)
from weblate.trans.models import Suggestion, Comment
from weblate.lang.models import Language


class NotificationTest(FixtureTestCase, RegistrationTestMixin):
    def setUp(self):
        super(NotificationTest, self).setUp()
        self.user.email = 'noreply+notify@weblate.org'
        self.user.save()
        czech = Language.objects.get(code='cs')
        profile = Profile.objects.get(user=self.user)
        profile.subscribe_any_translation = True
        profile.subscribe_new_string = True
        profile.subscribe_new_suggestion = True
        profile.subscribe_new_contributor = True
        profile.subscribe_new_comment = True
        profile.subscribe_new_language = True
        profile.subscribe_merge_failure = True
        profile.subscriptions.add(self.project)
        profile.languages.add(czech)
        profile.save()

    @staticmethod
    def second_user():
        return User.objects.create_user(
            'seconduser',
            'noreply+second@example.org',
            'testpassword'
        )

    @override_settings(ADMINS=(('Weblate test', 'noreply@weblate.org'), ))
    def test_notify_merge_failure(self):
        notify_merge_failure(
            self.component,
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
        self.component.project.add_user(self.second_user(), '@Administration')
        notify_merge_failure(
            self.component,
            'Failed merge',
            'Error\nstatus'
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 5)

    @override_settings(ADMINS=(('Weblate test', 'noreply@weblate.org'), ))
    def test_notify_parse_error(self):
        notify_parse_error(
            self.component,
            self.get_translation(),
            'Failed merge',
            'test/file.po',
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Parse error in Test/Test'
        )

        # Add project owner
        self.component.project.add_user(self.second_user(), '@Administration')
        notify_parse_error(
            self.component,
            self.get_translation(),
            'Error\nstatus',
            'test/file.po',
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
            self.component,
            Language.objects.filter(code='de'),
            second_user
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New language request in Test/Test'
        )

        # Add project owner
        self.component.project.add_user(second_user, '@Administration')
        notify_new_language(
            self.component,
            Language.objects.filter(code='de'),
            second_user,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 3)

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
                content_hash=unit.content_hash,
                project=unit.translation.component.project,
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
                content_hash=unit.content_hash,
                project=unit.translation.component.project,
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
                content_hash=unit.content_hash,
                project=unit.translation.component.project,
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

    def test_notify_account(self):
        request = self.get_request('/')
        notify_account_activity(request.user, request, 'password')
        self.assertEqual(len(mail.outbox), 1)
        self.assert_notify_mailbox(mail.outbox[0])

    def test_notify_html_language(self):
        profile = Profile.objects.get(user=self.user)
        profile.language = 'cs'
        profile.save()
        request = self.get_request('/')
        notify_account_activity(request.user, request, 'password')
        self.assertEqual(len(mail.outbox), 1)
        # There is just one (html) alternative
        self.assertIn('lang="cs"', mail.outbox[0].alternatives[0][0])
