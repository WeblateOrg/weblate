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

from unittest import TestCase as UnitTestCase
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.core import mail

from weblate.accounts.models import (
    Profile,
    notify_merge_failure,
    notify_parse_error,
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
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models.unitdata import Suggestion, Comment
from weblate.lang.models import Language


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

    def test_notify_parse_error(self):
        notify_parse_error(
            self.subproject,
            self.get_translation(),
            'Failed merge',
        )

        # Check mail (second one is for admin)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] Parse error in Test/Test'
        )

        # Add project owner
        self.subproject.project.owners.add(self.second_user())
        notify_parse_error(
            self.subproject,
            self.get_translation(),
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
