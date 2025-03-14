# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for notitifications."""

from __future__ import annotations

from copy import deepcopy

from django.conf import settings
from django.core import mail
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.accounts.models import AuditLog, Profile, Subscription
from weblate.accounts.notifications import (
    MergeFailureNotification,
    NotificationFrequency,
    NotificationScope,
)
from weblate.accounts.tasks import (
    notify_changes,
    notify_daily,
    notify_monthly,
    notify_weekly,
    send_mails,
)
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Announcement, Comment, Suggestion
from weblate.trans.tests.test_views import RegistrationTestMixin, ViewTestCase

TEMPLATES_RAISE = deepcopy(settings.TEMPLATES)
TEMPLATES_RAISE[0]["OPTIONS"]["string_if_invalid"] = "TEMPLATE_BUG[%s]"


@override_settings(TEMPLATES=TEMPLATES_RAISE)
class NotificationTest(ViewTestCase, RegistrationTestMixin):
    def setUp(self) -> None:
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
            "ComponentTranslatedNotificaton",
            "LanguageTranslatedNotificaton",
        )
        for notification in notifications:
            # Remove any conflicting notifications
            Subscription.objects.filter(
                user=self.user,
                scope=NotificationScope.SCOPE_WATCHED,
                notification=notification,
            ).delete()
            Subscription.objects.create(
                user=self.user,
                scope=NotificationScope.SCOPE_WATCHED,
                notification=notification,
                frequency=NotificationFrequency.FREQ_INSTANT,
            )
        self.thirduser = User.objects.create_user(
            "thirduser", "noreply+third@example.org", "testpassword"
        )

    def validate_notifications(
        self, count, subject: str | None = None, subjects: list[str] | None = None
    ) -> None:
        for i, message in enumerate(mail.outbox):
            self.assertNotIn("TEMPLATE_BUG", message.subject)
            self.assertNotIn("TEMPLATE_BUG", message.body)
            self.assertNotIn("TEMPLATE_BUG", message.alternatives[0][0])
            if subject:
                self.assertEqual(message.subject, subject)
            if subjects:
                self.assertEqual(message.subject, subjects[i])
        self.assertEqual(len(mail.outbox), count)

    def test_notify_lock(self) -> None:
        self.component.change_set.create(
            action=ActionEvents.LOCK,
        )
        self.validate_notifications(1, "[Weblate] Component Test/Test was locked")
        mail.outbox = []
        self.component.change_set.create(
            action=ActionEvents.UNLOCK,
        )
        self.validate_notifications(1, "[Weblate] Component Test/Test was unlocked")

    def test_notify_onetime(self) -> None:
        Subscription.objects.filter(notification="LockNotification").delete()
        Subscription.objects.create(
            user=self.user,
            scope=NotificationScope.SCOPE_WATCHED,
            notification="LockNotification",
            frequency=NotificationFrequency.FREQ_INSTANT,
            onetime=True,
        )
        self.component.change_set.create(
            action=ActionEvents.UNLOCK,
        )
        self.validate_notifications(1, "[Weblate] Component Test/Test was unlocked")
        mail.outbox = []
        self.component.change_set.create(
            action=ActionEvents.LOCK,
        )
        self.validate_notifications(0)
        self.assertFalse(
            Subscription.objects.filter(notification="LockNotification").exists()
        )

    def test_notify_license(self) -> None:
        self.component.license = "WTFPL"
        self.component.save()
        self.validate_notifications(1, "[Weblate] Test/Test was re-licensed to WTFPL")

    def test_notify_agreement(self) -> None:
        self.component.agreement = "You have to agree."
        self.component.save()
        self.validate_notifications(
            1, "[Weblate] Contributor license agreement for Test/Test was changed"
        )

    def test_notify_merge_failure(self) -> None:
        change = self.component.change_set.create(
            details={"error": "Failed merge", "status": "Error\nstatus"},
            action=ActionEvents.FAILED_MERGE,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(self.anotheruser, "Administration")
        notify_changes([change.pk])

        # Check mail
        self.validate_notifications(2, "[Weblate] Repository failure in Test/Test")

    def test_notify_repository(self) -> None:
        change = self.component.change_set.create(action=ActionEvents.MERGE)

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(self.anotheruser, "Administration")
        notify_changes([change.pk])

        # Check mail
        self.validate_notifications(2, "[Weblate] Repository operation in Test/Test")

    def test_notify_parse_error(self) -> None:
        change = self.get_translation().change_set.create(
            details={"error_message": "Failed merge", "filename": "test/file.po"},
            action=ActionEvents.PARSE_ERROR,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(self.anotheruser, "Administration")
        notify_changes([change.pk])

        # Check mail
        self.validate_notifications(3, "[Weblate] Parse error in Test/Test")

    def test_notify_new_string(self) -> None:
        unit = self.get_unit()
        unit.change_set.create(action=ActionEvents.NEW_UNIT)

        # Check mail
        self.validate_notifications(
            1, "[Weblate] String to translate in Test/Test — Czech"
        )

    def test_notify_new_translation(self) -> None:
        unit = self.get_unit()
        unit.change_set.create(
            user=self.anotheruser,
            old="",
            action=ActionEvents.CHANGE,
        )

        # Check mail - TranslatedStringNotificaton
        self.validate_notifications(1, "[Weblate] New translation in Test/Test — Czech")

    def test_notify_approved_translation(self) -> None:
        unit = self.get_unit()
        unit.change_set.create(
            user=self.anotheruser,
            old="",
            action=ActionEvents.APPROVE,
        )

        # Check mail - ApprovedStringNotificaton
        self.validate_notifications(
            1,
            subjects=[
                "[Weblate] Approved translation in Test/Test — Czech",
            ],
        )

    def test_notify_new_language(self) -> None:
        anotheruser = self.anotheruser
        change = self.component.change_set.create(
            user=anotheruser,
            details={"language": "de"},
            action=ActionEvents.REQUESTED_LANGUAGE,
        )

        # Check mail
        self.assertEqual(len(mail.outbox), 1)

        # Add project owner
        self.component.project.add_user(anotheruser, "Administration")
        notify_changes([change.pk])

        # Check mail
        self.validate_notifications(2, "[Weblate] New language request in Test/Test")

    def test_notify_new_contributor(self) -> None:
        unit = self.get_unit()
        unit.change_set.create(
            user=self.anotheruser,
            action=ActionEvents.NEW_CONTRIBUTOR,
        )

        # Check mail
        self.validate_notifications(1, "[Weblate] New contributor in Test/Test — Czech")

    def test_notify_new_suggestion(self) -> None:
        unit = self.get_unit()
        unit.change_set.create(
            suggestion=Suggestion.objects.create(unit=unit, target="Foo"),
            user=self.anotheruser,
            action=ActionEvents.SUGGESTION,
        )

        # Check mail
        self.validate_notifications(1, "[Weblate] New suggestion in Test/Test — Czech")

    def add_comment(self, comment="Foo", language="en") -> None:
        unit = self.get_unit(language=language)
        unit.change_set.create(
            comment=Comment.objects.create(unit=unit, comment=comment),
            user=self.thirduser,
            action=ActionEvents.COMMENT,
        )

    def test_notify_new_comment(self, expected=1, comment="Foo") -> None:
        self.add_comment(comment=comment)

        # Check mail
        self.validate_notifications(expected, "[Weblate] New comment in Test/Test")

    def test_notify_new_comment_language(self) -> None:
        # Subscribed language
        self.add_comment(language="cs")
        self.validate_notifications(1, "[Weblate] New comment in Test/Test")

        # Empty outbox
        mail.outbox = []

        # Unsubscribed language
        self.add_comment(language="de")
        self.assertEqual(len(mail.outbox), 0)

    def test_notify_new_comment_report(self) -> None:
        self.component.report_source_bugs = "noreply@weblate.org"
        self.component.save()
        self.test_notify_new_comment(2)

    def test_notify_new_comment_mention(self) -> None:
        self.test_notify_new_comment(
            2, f"Hello @{self.anotheruser.username} and @invalid"
        )

    def test_notify_new_comment_author(self) -> None:
        self.edit_unit("Hello, world!\n", "Ahoj svete!\n")
        # No notification for own edit
        self.assertEqual(len(mail.outbox), 0)
        change = self.get_unit().recent_content_changes[0]
        change.user = self.anotheruser
        change.save()
        # Notification for other user edit via  TranslatedStringNotificaton
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox = []

    def test_notify_new_component(self) -> None:
        self.component.change_set.create(action=ActionEvents.CREATE_COMPONENT)
        self.validate_notifications(1, "[Weblate] New translation component Test/Test")

    def test_notify_new_announcement(self) -> None:
        Announcement.objects.create(
            component=self.component,
            message="Hello word",
            notify=False,
        )
        self.validate_notifications(0)
        Announcement.objects.create(
            component=self.component,
            message="Hello word",
            notify=True,
        )
        self.validate_notifications(1, "[Weblate] New announcement on Test")
        mail.outbox = []
        Announcement.objects.create(
            component=self.component,
            language=Language.objects.get(code="cs"),
            message="Hello word",
            notify=True,
        )
        self.validate_notifications(1, "[Weblate] New announcement on Test")
        mail.outbox = []
        Announcement.objects.create(
            component=self.component,
            language=Language.objects.get(code="de"),
            message="Hello word",
            notify=True,
        )
        self.validate_notifications(0)
        mail.outbox = []
        Announcement.objects.create(
            message="Hello global word",
            notify=True,
        )
        self.validate_notifications(
            User.objects.filter(is_active=True).count(),
            "[Weblate] New announcement at Weblate",
        )

    def test_notify_component_translated(self) -> None:
        unit = self.get_unit()
        unit.translation.component.change_set.create(
            user=self.anotheruser,
            old="",
            action=ActionEvents.COMPLETED_COMPONENT,
        )

        # Check mail - TranslatedComponentNotification
        self.validate_notifications(
            1,
            "[Weblate] Translations in all languages have been completed in Test/Test",
        )

    def test_notify_language_translated(self) -> None:
        unit = self.get_unit(language="cs")
        unit.translation.change_set.create(
            user=self.anotheruser,
            action=ActionEvents.COMPLETE,
        )

        self.validate_notifications(1, "[Weblate] Test/Test — Czech has been completed")

    def test_notify_alert(self) -> None:
        self.component.project.add_user(self.user, "Administration")
        self.component.add_alert("PushFailure", error="Some error")
        self.validate_notifications(
            2,
            subjects=[
                "[Weblate] New alert on Test/Test",
                "[Weblate] Component Test/Test was locked",
            ],
        )

    def test_notify_alert_ignore(self) -> None:
        self.component.project.add_user(self.user, "Administration")
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

    def test_notify_account(self) -> None:
        request = self.get_request()
        AuditLog.objects.create(request.user, request, "password")
        self.assertEqual(len(mail.outbox), 1)
        self.assert_notify_mailbox(mail.outbox[0])
        # Verify site root expansion in email
        content = mail.outbox[0].alternatives[0][0]
        self.assertNotIn('href="/', content)

    def test_notify_html_language(self) -> None:
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
        frequency=NotificationFrequency.FREQ_DAILY,
        notify=notify_daily,
        change=ActionEvents.FAILED_MERGE,
        subj="Repository operation failed",
    ) -> None:
        Subscription.objects.filter(
            frequency=NotificationFrequency.FREQ_INSTANT,
            notification__in=("MergeFailureNotification", "NewTranslationNotificaton"),
        ).update(frequency=frequency)
        self.component.change_set.create(
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

    def test_digest_weekly(self) -> None:
        self.test_digest(NotificationFrequency.FREQ_WEEKLY, notify_weekly)

    def test_digest_monthly(self) -> None:
        self.test_digest(NotificationFrequency.FREQ_MONTHLY, notify_monthly)

    def test_digest_new_lang(self) -> None:
        self.test_digest(
            change=ActionEvents.REQUESTED_LANGUAGE,
            subj="New language was added or requested",
        )

    def test_reminder(
        self,
        frequency=NotificationFrequency.FREQ_DAILY,
        notify=notify_daily,
        notification="ToDoStringsNotification",
        subj="4 unfinished strings in Test/Test",
    ) -> None:
        self.user.subscription_set.filter(frequency=frequency).delete()
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_WATCHED,
            notification=notification,
            frequency=frequency,
        )
        # Check mail
        self.assertEqual(len(mail.outbox), 0)

        # Trigger notification
        notify()
        self.validate_notifications(1, f"[Weblate] {subj}")

    def test_reminder_weekly(self) -> None:
        self.test_reminder(NotificationFrequency.FREQ_WEEKLY, notify_weekly)

    def test_reminder_monthly(self) -> None:
        self.test_reminder(NotificationFrequency.FREQ_MONTHLY, notify_monthly)

    def test_reminder_suggestion(self) -> None:
        unit = self.get_unit()
        Suggestion.objects.create(unit=unit, target="Foo")
        self.test_reminder(
            notification="PendingSuggestionsNotification",
            subj="1 pending suggestion in Test/Test",
        )


class SubscriptionTest(ViewTestCase):
    notification = MergeFailureNotification

    def get_users(self, frequency):
        change = self.component.change_set.create(
            action=ActionEvents.FAILED_MERGE,
            details={"error": "error", "status": "status"},
        )
        notification = self.notification(None)
        return list(notification.get_users(frequency, change))

    def test_scopes(self) -> None:
        self.user.profile.watched.add(self.project)
        # Not subscriptions
        self.user.subscription_set.all().delete()
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 0)
        # Default subscription
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_WATCHED,
            notification=self.notification.get_name(),
            frequency=NotificationFrequency.FREQ_MONTHLY,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 1)
        # Admin subscription
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_ADMIN,
            notification=self.notification.get_name(),
            frequency=NotificationFrequency.FREQ_WEEKLY,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 1)

        self.component.project.add_user(self.user, "Administration")
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 1)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 0)
        # Project subscription
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_PROJECT,
            project=self.project,
            notification=self.notification.get_name(),
            frequency=NotificationFrequency.FREQ_DAILY,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 1)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 0)
        # Component subscription
        subscription = self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_COMPONENT,
            project=self.project,
            notification=self.notification.get_name(),
            frequency=NotificationFrequency.FREQ_INSTANT,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 1)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 0)
        # Disabled notification for component
        subscription.frequency = NotificationFrequency.FREQ_NONE
        subscription.save()
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 0)

    def test_all_scope(self) -> None:
        self.user.subscription_set.all().delete()
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 0)
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_ALL,
            notification=self.notification.get_name(),
            frequency=NotificationFrequency.FREQ_MONTHLY,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_DAILY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_WEEKLY)), 0)
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_MONTHLY)), 1)

    def test_skip(self) -> None:
        self.user.profile.watched.add(self.project)
        # Not subscriptions
        self.user.subscription_set.all().delete()
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)
        # Default subscription
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_WATCHED,
            notification=self.notification.get_name(),
            frequency=NotificationFrequency.FREQ_INSTANT,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 1)
        # Subscribe to parent event
        self.user.subscription_set.create(
            scope=NotificationScope.SCOPE_WATCHED,
            notification="NewAlertNotificaton",
            frequency=NotificationFrequency.FREQ_INSTANT,
        )
        self.assertEqual(len(self.get_users(NotificationFrequency.FREQ_INSTANT)), 0)


class SendMailsTest(SimpleTestCase):
    @override_settings(
        EMAIL_HOST="nonexisting.weblate.org",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    )
    def test_error_handling(self) -> None:
        send_mails([{}])
        self.assertEqual(len(mail.outbox), 0)
