#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

"""Tests for notitifications."""

from copy import deepcopy
from typing import List, Optional

from django.conf import settings
from django.core import mail
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.accounts.models import AuditLog, Profile, Subscription
from weblate.accounts.notifications import (
    FREQ_DAILY,
    FREQ_INSTANT,
    FREQ_MONTHLY,
    FREQ_NONE,
    FREQ_WEEKLY,
    SCOPE_ADMIN,
    SCOPE_ALL,
    SCOPE_COMPONENT,
    SCOPE_PROJECT,
    SCOPE_WATCHED,
    MergeFailureNotification,
)
from weblate.accounts.tasks import (
    notify_change,
    notify_daily,
    notify_monthly,
    notify_weekly,
    send_mails,
)
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Announcement, Change, Comment, Suggestion
from weblate.trans.tests.test_views import RegistrationTestMixin, ViewTestCase

TEMPLATES_RAISE = deepcopy(settings.TEMPLATES)
TEMPLATES_RAISE[0]["OPTIONS"]["string_if_invalid"] = "TEMPLATE_BUG[%s]"


@override_settings(TEMPLATES=TEMPLATES_RAISE)
class NotificationTest(ViewTestCase, RegistrationTestMixin):
    def setUp(self):
        super().setUp()
        self.user.email = "noreply+notify@weblate.org"
        self.user.save()
        czech = Language.objects.get(code="cs")
        profile = Profile.objects.get(user=self.user)
        profile.watched.add(self.project)
        profile.languages.add(czech)
        profile.save()
        notifications = (
            "MergeFailureNotification",
            "RepositoryNotification",
            "ParseErrorNotification",
            "NewStringNotificaton",
            "NewContributorNotificaton",
            "NewSuggestionNotificaton",
            "NewCommentNotificaton",
            "NewComponentNotificaton",
            "LockNotification",
            "LicenseNotification",
            "ChangedStringNotificaton",
            "TranslatedStringNotificaton",
            "ApprovedStringNotificaton",
            "NewTranslationNotificaton",
            "MentionCommentNotificaton",
            "LastAuthorCommentNotificaton",
        )
        for notification in notifications:
            Subscription.objects.create(
                user=self.user,
                scope=SCOPE_WATCHED,
                notification=notification,
                frequency=FREQ_INSTANT,
            )
        self.thirduser = User.objects.create_user(
            "thirduser", "noreply+third@example.org", "testpassword"
        )

    def validate_notifications(
        self, count, subject: Optional[str] = None, subjects: Optional[List[str]] = None
    ):
        for i, message in enumerate(mail.outbox):
            self.assertNotIn("TEMPLATE_BUG", message.subject)
            self.assertNotIn("TEMPLATE_BUG", message.body)
            self.assertNotIn("TEMPLATE_BUG", message.alternatives[0][0])
            if subject:
                self.assertEqual(message.subject, subject)
            if subjects:
                self.assertEqual(message.subject, subjects[i])
        self.assertEqual(len(mail.outbox), count)

    def test_notify_lock(self):
        Change.objects.create(
            component=self.component,
            action=Change.ACTION_LOCK,
        )
        self.validate_notifications(1, "[Weblate] Component Test/Test was locked")
        mail.outbox = []
        Change.objects.create(
            component=self.component,
            action=Change.ACTION_UNLOCK,
        )
        self.validate_notifications(1, "[Weblate] Component Test/Test was unlocked")

    def test_notify_onetime(self):
        Subscription.objects.filter(notification="LockNotification").delete()
        Subscription.objects.create(
            user=self.user,
            scope=SCOPE_WATCHED,
            notification="LockNotification",
            frequency=FREQ_INSTANT,
            onetime=True,
        )
        Change.objects.create(
            component=self.component,
            action=Change.ACTION_UNLOCK,
        )
        self.validate_notifications(1, "[Weblate] Component Test/Test was unlocked")
        mail.outbox = []
        Change.objects.create(
            component=self.component,
            action=Change.ACTION_LOCK,
        )
        self.validate_notifications(0)
        self.assertFalse(
            Subscription.objects.filter(notification="LockNotification").exists()
        )

    def test_notify_license(self):
        self.component.license = "WTFPL"
        self.component.save()
        self.validate_notifications(1, "[Weblate] Test/Test was re-licensed to WTFPL")

    def test_notify_agreement(self):
        self.component.agreement = "You have to agree."
        self.component.save()
        self.validate_notifications(
            1, "[Weblate] Contributor agreement for Test/Test was changed"
        )

    def test_notify_merge_failure(self):
        change = Change.objects.create(
            component=self.component,
            details={"error": "Failed merge", "status": "Error\nstatus"},
            action=Change.ACTION_FAILED_MERGE,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(self.anotheruser, "@Administration")
        notify_change(change.pk)

        # Check mail
        self.validate_notifications(2, "[Weblate] Repository failure in Test/Test")

    def test_notify_repository(self):
        change = Change.objects.create(
            component=self.component, action=Change.ACTION_MERGE
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(self.anotheruser, "@Administration")
        notify_change(change.pk)

        # Check mail
        self.validate_notifications(2, "[Weblate] Repository operation in Test/Test")

    def test_notify_parse_error(self):
        change = Change.objects.create(
            translation=self.get_translation(),
            details={"error_message": "Failed merge", "filename": "test/file.po"},
            action=Change.ACTION_PARSE_ERROR,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(self.anotheruser, "@Administration")
        notify_change(change.pk)

        # Check mail
        self.validate_notifications(3, "[Weblate] Parse error in Test/Test")

    def test_notify_new_string(self):
        Change.objects.create(
            translation=self.get_translation(), action=Change.ACTION_NEW_STRING
        )

        # Check mail
        self.validate_notifications(
            1, "[Weblate] New string to translate in Test/Test — Czech"
        )

    def test_notify_new_strings(self):
        Change.objects.create(
            translation=self.get_translation(),
            action=Change.ACTION_NEW_STRING,
            details={"count": 10},
        )

        # Check mail
        self.validate_notifications(
            1, "[Weblate] New strings to translate in Test/Test — Czech"
        )

    def test_notify_new_translation(self):
        Change.objects.create(
            unit=self.get_unit(),
            user=self.anotheruser,
            old="",
            action=Change.ACTION_CHANGE,
        )

        # Check mail - ChangedStringNotificaton and TranslatedStringNotificaton
        self.validate_notifications(2, "[Weblate] New translation in Test/Test — Czech")

    def test_notify_approved_translation(self):
        Change.objects.create(
            unit=self.get_unit(),
            user=self.anotheruser,
            old="",
            action=Change.ACTION_APPROVE,
        )

        # Check mail - ChangedStringNotificaton and ApprovedStringNotificaton
        self.validate_notifications(
            2,
            subjects=[
                "[Weblate] New translation in Test/Test — Czech",
                "[Weblate] Approved translation in Test/Test — Czech",
            ],
        )

    def test_notify_new_language(self):
        anotheruser = self.anotheruser
        change = Change.objects.create(
            user=anotheruser,
            component=self.component,
            details={"language": "de"},
            action=Change.ACTION_REQUESTED_LANGUAGE,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(anotheruser, "@Administration")
        notify_change(change.pk)

        # Check mail
        self.validate_notifications(2, "[Weblate] New language request in Test/Test")

    def test_notify_new_contributor(self):
        Change.objects.create(
            unit=self.get_unit(),
            user=self.anotheruser,
            action=Change.ACTION_NEW_CONTRIBUTOR,
        )

        # Check mail
        self.validate_notifications(1, "[Weblate] New contributor in Test/Test — Czech")

    def test_notify_new_suggestion(self):
        unit = self.get_unit()
        Change.objects.create(
            unit=unit,
            suggestion=Suggestion.objects.create(unit=unit, target="Foo"),
            user=self.anotheruser,
            action=Change.ACTION_SUGGESTION,
        )

        # Check mail
        self.validate_notifications(1, "[Weblate] New suggestion in Test/Test — Czech")

    def add_comment(self, comment="Foo", language="en"):
        unit = self.get_unit(language=language)
        Change.objects.create(
            unit=unit,
            comment=Comment.objects.create(unit=unit, comment=comment),
            user=self.thirduser,
            action=Change.ACTION_COMMENT,
        )

    def test_notify_new_comment(self, expected=1, comment="Foo"):
        self.add_comment(comment=comment)

        # Check mail
        self.validate_notifications(expected, "[Weblate] New comment in Test/Test")

    def test_notify_new_comment_language(self):
        # Subscribed language
        self.add_comment(language="cs")
        self.validate_notifications(1, "[Weblate] New comment in Test/Test")

        # Empty outbox
        mail.outbox = []

        # Unsubscribed language
        self.add_comment(language="de")
        self.assertEqual(len(mail.outbox), 0)

    def test_notify_new_comment_report(self):
        self.component.report_source_bugs = "noreply@weblate.org"
        self.component.save()
        self.test_notify_new_comment(2)

    def test_notify_new_comment_mention(self):
        self.test_notify_new_comment(
            2, f"Hello @{self.anotheruser.username} and @invalid"
        )

    def test_notify_new_comment_author(self):
        self.edit_unit("Hello, world!\n", "Ahoj svete!\n")
        # No notification for own edit
        self.assertEqual(len(mail.outbox), 0)
        change = self.get_unit().recent_content_changes[0]
        change.user = self.anotheruser
        change.save()
        # Notification for other user edit
        # ChangedStringNotificaton and TranslatedStringNotificaton
        self.assertEqual(len(mail.outbox), 2)
        mail.outbox = []

    def test_notify_new_component(self):
        Change.objects.create(
            component=self.component, action=Change.ACTION_CREATE_COMPONENT
        )
        self.validate_notifications(1, "[Weblate] New translation component Test/Test")

    def test_notify_new_announcement(self):
        Announcement.objects.create(component=self.component, message="Hello word")
        self.validate_notifications(1, "[Weblate] New announcement on Test")
        mail.outbox = []
        Announcement.objects.create(message="Hello global word")
        self.validate_notifications(
            User.objects.filter(is_active=True).count(),
            "[Weblate] New announcement at Weblate",
        )

    def test_notify_alert(self):
        self.component.project.add_user(self.user, "@Administration")
        self.component.add_alert("PushFailure", error="Some error")
        self.validate_notifications(
            2,
            subjects=[
                "[Weblate] New alert on Test/Test",
                "[Weblate] Component Test/Test was locked",
            ],
        )

    def test_notify_alert_ignore(self):
        self.component.project.add_user(self.user, "@Administration")
        # Create linked component, this triggers missing license alert
        self.create_link_existing()
        mail.outbox = []
        self.component.add_alert("PushFailure", error="Some error")
        self.validate_notifications(
            3,
            subjects=[
                "[Weblate] New alert on Test/Test",
                "[Weblate] Component Test/Test was locked",
                "[Weblate] Component Test/Test2 was locked",
            ],
        )

    def test_notify_account(self):
        request = self.get_request()
        AuditLog.objects.create(request.user, request, "password")
        self.assertEqual(len(mail.outbox), 1)
        self.assert_notify_mailbox(mail.outbox[0])
        # Verify site root expansion in email
        content = mail.outbox[0].alternatives[0][0]
        self.assertNotIn('href="/', content)

    def test_notify_html_language(self):
        self.user.profile.language = "cs"
        self.user.profile.save()
        request = self.get_request()
        AuditLog.objects.create(request.user, request, "password")
        self.assertEqual(len(mail.outbox), 1)
        # There is just one (html) alternative
        content = mail.outbox[0].alternatives[0][0]
        self.assertIn('lang="cs"', content)
        self.assertIn("změněno", content)

    def test_digest(
        self,
        frequency=FREQ_DAILY,
        notify=notify_daily,
        change=Change.ACTION_FAILED_MERGE,
        subj="Repository failure",
    ):
        Subscription.objects.filter(
            frequency=FREQ_INSTANT,
            notification__in=("MergeFailureNotification", "NewTranslationNotificaton"),
        ).update(frequency=frequency)
        Change.objects.create(
            component=self.component,
            details={
                "error": "Failed merge",
                "status": "Error\nstatus",
                "language": "de",
            },
            action=change,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 0)

        # Trigger notification
        notify()
        self.validate_notifications(1, f"[Weblate] Digest: {subj}")
        content = mail.outbox[0].alternatives[0][0]
        self.assertNotIn('img src="/', content)

    def test_digest_weekly(self):
        self.test_digest(FREQ_WEEKLY, notify_weekly)

    def test_digest_monthly(self):
        self.test_digest(FREQ_MONTHLY, notify_monthly)

    def test_digest_new_lang(self):
        self.test_digest(change=Change.ACTION_REQUESTED_LANGUAGE, subj="New language")

    def test_reminder(
        self,
        frequency=FREQ_DAILY,
        notify=notify_daily,
        notification="ToDoStringsNotification",
        subj="4 strings needing action in Test/Test",
    ):
        self.user.subscription_set.create(
            scope=SCOPE_WATCHED, notification=notification, frequency=frequency
        )
        # Check mail
        self.assertEqual(len(mail.outbox), 0)

        # Trigger notification
        notify()
        self.validate_notifications(1, f"[Weblate] {subj}")

    def test_reminder_weekly(self):
        self.test_reminder(FREQ_WEEKLY, notify_weekly)

    def test_reminder_monthly(self):
        self.test_reminder(FREQ_MONTHLY, notify_monthly)

    def test_reminder_suggestion(self):
        unit = self.get_unit()
        Suggestion.objects.create(unit=unit, target="Foo")
        self.test_reminder(
            notification="PendingSuggestionsNotification",
            subj="1 pending suggestion in Test/Test",
        )


class SubscriptionTest(ViewTestCase):
    notification = MergeFailureNotification

    def get_users(self, frequency):
        change = Change.objects.create(
            action=Change.ACTION_FAILED_MERGE, component=self.component
        )
        notification = self.notification(None)
        return list(notification.get_users(frequency, change))

    def test_scopes(self):
        self.user.profile.watched.add(self.project)
        # Not subscriptions
        self.user.subscription_set.all().delete()
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 0)
        # Default subscription
        self.user.subscription_set.create(
            scope=SCOPE_WATCHED,
            notification=self.notification.get_name(),
            frequency=FREQ_MONTHLY,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 1)
        # Admin subscription
        self.user.subscription_set.create(
            scope=SCOPE_ADMIN,
            notification=self.notification.get_name(),
            frequency=FREQ_WEEKLY,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 1)

        self.component.project.add_user(self.user, "@Administration")
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 1)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 0)
        # Project subscription
        self.user.subscription_set.create(
            scope=SCOPE_PROJECT,
            project=self.project,
            notification=self.notification.get_name(),
            frequency=FREQ_DAILY,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 1)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 0)
        # Component subscription
        subscription = self.user.subscription_set.create(
            scope=SCOPE_COMPONENT,
            project=self.project,
            notification=self.notification.get_name(),
            frequency=FREQ_INSTANT,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 1)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 0)
        # Disabled notification for component
        subscription.frequency = FREQ_NONE
        subscription.save()
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 0)

    def test_all_scope(self):
        self.user.subscription_set.all().delete()
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 0)
        self.user.subscription_set.create(
            scope=SCOPE_ALL,
            notification=self.notification.get_name(),
            frequency=FREQ_MONTHLY,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(FREQ_MONTHLY)), 1)

    def test_skip(self):
        self.user.profile.watched.add(self.project)
        # Not subscriptions
        self.user.subscription_set.all().delete()
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)
        # Default subscription
        self.user.subscription_set.create(
            scope=SCOPE_WATCHED,
            notification=self.notification.get_name(),
            frequency=FREQ_INSTANT,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 1)
        # Subscribe to parent event
        self.user.subscription_set.create(
            scope=SCOPE_WATCHED,
            notification="NewAlertNotificaton",
            frequency=FREQ_INSTANT,
        )
        self.assertEqual(len(self.get_users(FREQ_INSTANT)), 0)


class SendMailsTest(SimpleTestCase):
    @override_settings(
        EMAIL_HOST="nonexisting.weblate.org",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    )
    def test_error_handling(self):
        send_mails([{}])
        self.assertEqual(len(mail.outbox), 0)
