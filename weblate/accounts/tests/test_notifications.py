# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.core import mail

from weblate.auth.models import User
from weblate.accounts.models import Profile, AuditLog
from weblate.accounts.notifications import (
    notify_merge_failure,
    notify_parse_error,
    notify_new_string,
    notify_new_suggestion,
    notify_new_comment,
    notify_new_translation,
    notify_new_contributor,
    notify_new_language,
)
from weblate.trans.tests.test_views import (
    ViewTestCase, RegistrationTestMixin,
)
from weblate.trans.models import Suggestion, Comment, Change
from weblate.lang.models import Language


class NotificationTest(ViewTestCase, RegistrationTestMixin):
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

    def test_notify_merge_failure(self):
        change = Change(
            component=self.component,
            details={
                'error': 'Failed merge',
                'status': 'Error\nstatus',
            },
        )
        notify_merge_failure(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Merge failure in Test/Test'
        )

        # Add project owner
        self.component.project.add_user(self.second_user(), '@Administration')
        notify_merge_failure(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 3)

    def test_notify_parse_error(self):
        change = Change(
            component=self.component,
            translation=self.get_translation(),
            details={
                'error': 'Failed merge',
                'filename': 'test/file.po',
            },
        )
        notify_parse_error(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Parse error in Test/Test'
        )

        # Add project owner
        self.component.project.add_user(self.second_user(), '@Administration')
        notify_parse_error(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 3)

    def test_notify_new_string(self):
        change = Change(translation=self.get_translation())
        notify_new_string(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New string to translate in Test/Test - Czech'
        )

    def test_notify_new_translation(self):
        change = Change(
            unit=self.get_unit(),
            user=self.second_user(),
            old='',
        )
        notify_new_translation(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New translation in Test/Test - Czech'
        )

    def test_notify_new_language(self):
        second_user = self.second_user()
        change = Change(
            user=second_user,
            component=self.component,
            details={'language': 'de'}
        )
        notify_new_language(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New language request in Test/Test'
        )

        # Add project owner
        self.component.project.add_user(second_user, '@Administration')
        notify_new_language(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 3)

    def test_notify_new_contributor(self):
        change = Change(unit=self.get_unit(), user=self.second_user())
        notify_new_contributor(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New contributor in Test/Test - Czech'
        )

    def test_notify_new_suggestion(self):
        unit = self.get_unit()
        change = Change(
            unit=unit,
            suggestion=Suggestion.objects.create(
                content_hash=unit.content_hash,
                project=unit.translation.component.project,
                language=unit.translation.language,
                target='Foo'
            ),
            user=self.second_user()
        )
        notify_new_suggestion(change)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New suggestion in Test/Test - Czech'
        )

    def test_notify_new_comment(self, expected=1, comment='Foo'):
        unit = self.get_unit()
        change = Change(
            unit=unit,
            comment=Comment.objects.create(
                content_hash=unit.content_hash,
                project=unit.translation.component.project,
                comment=comment,
            ),
            user=self.second_user()
        )
        notify_new_comment(change)

        # Check mail
        self.assertEqual(len(mail.outbox), expected)
        for message in mail.outbox:
            self.assertEqual(
                message.subject, '[Weblate] New comment in Test/Test'
            )

    def test_notify_new_comment_report(self):
        self.component.report_source_bugs = 'noreply@weblate.org'
        self.component.save()
        self.test_notify_new_comment(2)

    def test_notify_new_comment_mention(self):
        self.test_notify_new_comment(
            2,
            'Hello @{} and @invalid'.format(self.anotheruser.username)
        )

    def test_notify_new_comment_author(self):
        self.edit_unit('Hello, world!\n', 'Ahoj svete!\n')
        change = self.get_unit().change_set.content().order_by('-timestamp')[0]
        change.author = self.anotheruser
        change.save()
        self.test_notify_new_comment(2)

    def test_notify_account(self):
        request = self.get_request()
        AuditLog.objects.create(request.user, request, 'password')
        self.assertEqual(len(mail.outbox), 1)
        self.assert_notify_mailbox(mail.outbox[0])

    def test_notify_html_language(self):
        self.user.profile.language = 'cs'
        self.user.profile.save()
        request = self.get_request()
        AuditLog.objects.create(request.user, request, 'password')
        self.assertEqual(len(mail.outbox), 1)
        # There is just one (html) alternative
        content = mail.outbox[0].alternatives[0][0]
        self.assertIn('lang="cs"', content)
        self.assertIn('změněno', content)
