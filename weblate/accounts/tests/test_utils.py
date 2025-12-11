# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for various helper utilities."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.test.utils import override_settings

from weblate.accounts.models import format_private_email
from weblate.accounts.pipeline import slugify_username
from weblate.accounts.tasks import cleanup_auditlog, cleanup_social_auth
from weblate.utils.validators import EmailValidator, validate_username


class PipelineTest(SimpleTestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify_username("zkouska"), "zkouska")
        self.assertEqual(slugify_username("Zkouska"), "Zkouska")
        self.assertEqual(slugify_username("zkouška"), "zkouska")
        self.assertEqual(slugify_username(" zkouska "), "zkouska")
        self.assertEqual(slugify_username("ahoj - ahoj"), "ahoj-ahoj")
        self.assertEqual(slugify_username("..test"), "test")


class TasksTest(TestCase):
    def test_cleanup_social_auth(self) -> None:
        cleanup_social_auth()

    def test_cleanup_auditlog(self) -> None:
        cleanup_auditlog()


@override_settings(
    PRIVATE_COMMIT_EMAIL_TEMPLATE="{username}@users.noreply.{site_domain}",
    SITE_DOMAIN="example.com",
)
class FormatPrivateMainTestCase(SimpleTestCase):
    def validate_email(self, username: str, expected: str) -> None:
        # Make sure username is valid
        if username:
            validate_username(username)
        # Generate e-mail
        email = format_private_email(username, 99)
        # Validate e-mail
        EmailValidator()(email)
        # Make sure it is expected one
        self.assertEqual(email, expected)

    def test_format_private_email(self) -> None:
        self.validate_email("testuser", "testuser@users.noreply.example.com")

    @override_settings(SITE_DOMAIN="example.com:8080")
    def test_format_private_email_port(self) -> None:
        self.validate_email("testuser", "testuser@users.noreply.example.com")

    def test_format_private_email_dot(self) -> None:
        self.validate_email("testuser.", "testuser_@users.noreply.example.com")
        self.validate_email("testuser....", "testuser____@users.noreply.example.com")

    def test_format_private_email_blank(self) -> None:
        self.validate_email("", "user-99@users.noreply.example.com")

    def test_format_private_email_unicode(self) -> None:
        self.validate_email("zkouška", "zkouska@users.noreply.example.com")
