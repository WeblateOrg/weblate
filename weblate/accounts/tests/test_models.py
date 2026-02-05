# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for models (AuditLog and Profile)."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings

from weblate.accounts.models import AuditLog, Profile
from weblate.auth.models import User


class AuditLogTestCase(SimpleTestCase):
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
