# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for models (AuditLog and Profile)."""

from __future__ import annotations

from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import override_settings
from django.utils.translation import override

from weblate.accounts.admin import AuditLogAdmin
from weblate.accounts.models import (
    AUDIT_WARNING,
    LISTING_COLUMN_CHOICES,
    MAX_LISTING_COLUMNS,
    NOTIFY_ACTIVITY,
    AuditLog,
    Profile,
    validate_listing_columns,
)
from weblate.accounts.tasks import notify_auditlog
from weblate.accounts.utils import remove_user
from weblate.auth.models import User


class AuditLogTestCase(SimpleTestCase):
    def test_actor_and_guidance_are_escaped(self) -> None:
        audit = AuditLog(
            activity="blocked", params={"username": "<admin>", "project": "Test"}
        )
        message = audit.get_extra_message()
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("Triggered by <code>&lt;admin&gt;</code>.", message)
        self.assertIn("Please contact project maintainers", message)

    def test_actor_is_not_repeated(self) -> None:
        for activity in ("team-add", "sitewide-team-remove", "invited", "accepted"):
            with self.subTest(activity=activity):
                audit = AuditLog(activity=activity, params={"username": "admin"})
                self.assertIsNone(audit.get_extra_message())

    def test_legacy_entry_without_actor(self) -> None:
        audit = AuditLog(activity="superuser-granted", params={})
        self.assertIsNone(audit.get_extra_message())
        self.assertEqual(audit.get_message(), "Superuser privileges granted.")

    def test_address_ipv4(self) -> None:
        audit = AuditLog(address="127.0.0.1")
        self.assertEqual(audit.shortened_address, "127.0.0.0")

    def test_address_ipv6_local(self) -> None:
        audit = AuditLog(address="fe80::54c2:1234:5678:90ab")
        self.assertEqual(audit.shortened_address, "fe80::")

    def test_address_ipv6_weblate(self) -> None:
        audit = AuditLog(address="2a01:4f8:c0c:a84b::1")
        self.assertEqual(audit.shortened_address, "2a01:4f8:c0c::")

    def test_address_blank(self) -> None:
        audit = AuditLog()
        self.assertEqual(audit.shortened_address, "")

    def test_superuser_audit_classification(self) -> None:
        self.assertIn("superuser-granted", AUDIT_WARNING)
        self.assertIn("superuser-revoked", AUDIT_WARNING)
        self.assertIn("superuser-granted", NOTIFY_ACTIVITY)
        self.assertIn("superuser-revoked", NOTIFY_ACTIVITY)

    def test_rate_limit_audit_classification(self) -> None:
        self.assertNotIn("rate-limit", AUDIT_WARNING)
        self.assertNotIn("rate-limit", NOTIFY_ACTIVITY)

    def test_user_agent_display_empty(self) -> None:
        audit = AuditLog(user_agent="")
        self.assertEqual(audit.get_user_agent_display(), "")

    def test_user_agent_display(self) -> None:
        audit = AuditLog(user_agent="PC / Linux / Chrome 120.0.0")
        self.assertEqual(audit.get_user_agent_display(), "PC / Linux / Chrome 120.0.0")

    def test_user_agent_display_localizes_first_part_via_mapping(self) -> None:
        with mock.patch.dict(
            "weblate.accounts.models.USER_AGENT_DEVICE_TYPES",
            {"PC": "Translated PC"},
            clear=False,
        ):
            audit = AuditLog(user_agent="PC / Linux / Chrome 120.0.0")
            result = audit.get_user_agent_display()
            self.assertEqual(result, "Translated PC / Linux / Chrome 120.0.0")


class ListingColumnsValidationTestCase(SimpleTestCase):
    def test_valid(self) -> None:
        validate_listing_columns([])
        validate_listing_columns([column for column, _name in LISTING_COLUMN_CHOICES])

    def test_invalid(self) -> None:
        for value in (
            "comments",
            ["invalid"],
            ["comments", "comments"],
            ["comments"] * (MAX_LISTING_COLUMNS + 1),
            [["comments"]],
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_listing_columns(value)


class AuditLogLoggingTestCase(TestCase):
    def test_request_actor_and_privacy(self) -> None:
        user = User.objects.create_user("target", "target@example.com")
        actor = User.objects.create_user("admin", "admin@example.com")
        request = RequestFactory().post("/", HTTP_USER_AGENT="Admin browser")
        request.user = actor
        audit = AuditLog.objects.create(user, request, "admin-locked")
        self.assertEqual(audit.params["username"], actor.username)
        self.assertIsNone(audit.address)
        self.assertEqual(audit.user_agent, "")

        request.user = user
        audit = AuditLog.objects.create(user, request, "password")
        self.assertNotIn("username", audit.params)
        self.assertEqual(audit.address, "127.0.0.1")
        self.assertEqual(audit.user_agent, "Other / Other / Other")

        request.user = AnonymousUser()
        audit = AuditLog.objects.create(user, request, "reset-request")
        self.assertNotIn("username", audit.params)
        self.assertEqual(audit.address, "127.0.0.1")

        audit = AuditLog.objects.create(user, None, "disabled-expiry")
        self.assertNotIn("username", audit.params)

    def test_explicit_actor_and_existing_username(self) -> None:
        user = User.objects.create_user("target", "target@example.com")
        actor = User.objects.create_user("inviter", "inviter@example.com")
        request = RequestFactory().post("/")
        request.user = user
        audit = AuditLog.objects.create(user, request, "superuser-granted", actor=actor)
        self.assertEqual(audit.params["username"], actor.username)
        audit = AuditLog.objects.create(
            user, request, "accepted", username=actor.username
        )
        self.assertEqual(audit.params["username"], actor.username)

    def test_authentication_events_do_not_disclose_request_user(self) -> None:
        user = User.objects.create_user("target", "target@example.com")
        actor = User.objects.create_user("requester", "requester@example.com")
        request = RequestFactory().post("/")
        request.user = actor
        for activity in ("connect", "register", "failed-auth", "reset-request"):
            with self.subTest(activity=activity):
                audit = AuditLog.objects.create(user, request, activity)
                self.assertNotIn("username", audit.params)
                self.assertNotIn("requester", str(audit.get_extra_message()))

    def test_actor_in_notification(self) -> None:
        user = User.objects.create_user("target", "target@example.com")
        user.profile.language = "en"
        user.profile.save(update_fields=["language"])
        actor = User.objects.create_user("admin", "admin@example.com")
        audit = AuditLog.objects.create(user, None, "superuser-granted", actor=actor)
        with override("cs"):
            notify_auditlog(audit.pk, user.email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("admin", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].body.count("Triggered by"), 1)

    def test_sitewide_team_add_logged(self) -> None:
        user = User.objects.create_user(
            username="audit-user",
            email="audit-user@example.com",
        )

        with self.assertLogs("weblate.audit", level="INFO") as captured:
            AuditLog.objects.create(
                user, None, "sitewide-team-add", team="Users", username="admin"
            )

        self.assertTrue(
            any("audit[sitewide-team-add]" in entry for entry in captured.output)
        )


class RemovedAccountAuditTestCase(TestCase):
    def setUp(self) -> None:
        self.email = "Removed.User@example.com"
        self.user = User.objects.create_user(
            username="removed-user",
            email=self.email,
        )

    def test_removed_email_is_retained(self) -> None:
        remove_user(self.user, None)

        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, self.email)
        audit = self.user.auditlog_set.get(activity="removed")
        self.assertEqual(audit.params["email"], self.email)
        self.assertTrue(
            AuditLog.objects.filter(
                activity="removed", params__email__iexact=self.email.upper()
            ).exists()
        )

    def test_other_removal_activity_does_not_retain_email(self) -> None:
        remove_user(self.user, None, activity="token-removed", project="Test")

        audit = self.user.auditlog_set.get(activity="token-removed")
        self.assertNotIn("email", audit.params)

    def test_admin_search_finds_removed_email(self) -> None:
        remove_user(self.user, None)
        audit = self.user.auditlog_set.get(activity="removed")
        model_admin = AuditLogAdmin(AuditLog, AdminSite())

        result, _ = model_admin.get_search_results(
            RequestFactory().get("/"),
            AuditLog.objects.filter(activity="removed"),
            self.email.lower(),
        )

        self.assertSequenceEqual(list(result), [audit])


class ProfileCommitNameTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="testuser",
            full_name="Test User",
            email="test@example.com",
        )
        self.profile = self.user.profile

    @override_settings(
        PRIVATE_COMMIT_NAME_TEMPLATE="{site_title} user {user_id} from {site_domain}",
        SITE_TITLE="WeblateTest",
        SITE_DOMAIN="weblate.test:8080",
    )
    def test_get_site_commit_name(self) -> None:
        name = self.profile.get_site_commit_name()
        self.assertEqual(name, f"WeblateTest user {self.user.pk} from weblate.test")

    @override_settings(
        PRIVATE_COMMIT_NAME_TEMPLATE="Anonymous {username}",
        PRIVATE_COMMIT_NAME_OPT_IN=False,
    )
    def test_get_commit_name_default_private(self) -> None:
        self.profile.commit_name = Profile.CommitNameChoices.DEFAULT
        self.assertEqual(self.profile.get_commit_name(), "Anonymous testuser")

    @override_settings(
        PRIVATE_COMMIT_NAME_TEMPLATE="Anonymous {user_id}",
        PRIVATE_COMMIT_NAME_OPT_IN=True,
    )
    def test_get_commit_name_default_public(self) -> None:
        self.profile.commit_name = Profile.CommitNameChoices.DEFAULT
        self.assertEqual(self.profile.get_commit_name(), "Test User")

    def test_get_commit_name_explicit_public(self) -> None:
        self.profile.commit_name = Profile.CommitNameChoices.PUBLIC
        self.assertEqual(self.profile.get_commit_name(), "Test User")

    @override_settings(PRIVATE_COMMIT_NAME_TEMPLATE="Hidden Name")
    def test_get_commit_name_explicit_private(self) -> None:
        self.profile.commit_name = Profile.CommitNameChoices.PRIVATE
        self.assertEqual(self.profile.get_commit_name(), "Hidden Name")

    @override_settings(
        PRIVATE_COMMIT_NAME_TEMPLATE="Anon",
        PRIVATE_COMMIT_NAME_OPT_IN=False,
    )
    def test_bot_naming_remains_visible(self) -> None:
        self.user.is_bot = True
        self.user.save()
        self.profile.commit_name = Profile.CommitNameChoices.DEFAULT
        self.assertEqual(self.profile.get_commit_name(), "Test User")

    @override_settings(
        PRIVATE_COMMIT_NAME_TEMPLATE="Hidden",
        PRIVATE_COMMIT_NAME_OPT_IN=True,
    )
    def test_get_commit_name_explicit_private_ignores_global_public(self) -> None:
        self.profile.commit_name = Profile.CommitNameChoices.PRIVATE
        self.assertEqual(self.profile.get_commit_name(), "Hidden")

    @override_settings(
        PRIVATE_COMMIT_NAME_TEMPLATE="",
        PRIVATE_COMMIT_NAME_OPT_IN=False,
    )
    def test_get_commit_name_empty_template_fallback(self) -> None:
        self.profile.commit_name = Profile.CommitNameChoices.PRIVATE
        self.assertEqual(self.profile.get_commit_name(), "Test User")


class ProfileTMTestCase(TestCase):
    @override_settings(DEFAULT_AUTOCLEAN_TM=True)
    def test_default_tm_with_autoclean(self) -> None:
        """Test that TM is disabled by default when autoclean is on."""
        user = User.objects.create_user(username="testautoclean")
        user.refresh_from_db()
        self.assertFalse(user.profile.contribute_personal_tm)

    @override_settings(DEFAULT_AUTOCLEAN_TM=False)
    def test_default_tm_without_autoclean(self) -> None:
        """Test that TM is enabled by default when autoclean is off."""
        user = User.objects.create_user(username="testnoautoclean")
        user.refresh_from_db()
        self.assertTrue(user.profile.contribute_personal_tm)
