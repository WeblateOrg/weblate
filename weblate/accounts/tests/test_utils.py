# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for various helper utilities."""

from __future__ import annotations

from unittest import mock

from django.conf import settings
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import override_settings
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from weblate.accounts.models import format_private_commit_data
from weblate.accounts.pipeline import slugify_username
from weblate.accounts.tasks import cleanup_auditlog, cleanup_social_auth
from weblate.accounts.utils import (
    SESSION_EXPIRY_AGE,
    SESSION_EXPIRY_REFRESHED,
    SESSION_EXPIRY_SCOPE,
    SESSION_EXPIRY_SCOPE_2FA,
    SESSION_EXPIRY_SCOPE_AUTHENTICATED,
    SESSION_EXPIRY_SCOPE_LOGIN,
    SESSION_EXPIRY_SCOPE_SAML,
    adjust_session_expiry,
    get_session_expiry_refresh_seconds,
)
from weblate.auth.models import User
from weblate.utils.validators import EmailValidator, validate_username


class PipelineTest(SimpleTestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify_username("zkouska"), "zkouska")
        self.assertEqual(slugify_username("Zkouska"), "Zkouska")
        self.assertEqual(slugify_username("zkouška"), "zkouska")
        self.assertEqual(slugify_username(" zkouska "), "zkouska")
        self.assertEqual(slugify_username("ahoj - ahoj"), "ahoj-ahoj")
        self.assertEqual(slugify_username("..test"), "test")


class SessionExpiryTest(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )

    def get_request(self, data: dict[str, str] | None = None):
        request = self.factory.post("/", data or {})
        request.session = SessionStore()
        return request

    @override_settings(SESSION_COOKIE_AGE=1000, SESSION_COOKIE_AGE_AUTHENTICATED=1200)
    def test_authenticated_session_expiry_is_throttled(self) -> None:
        request = self.get_request()

        with mock.patch("weblate.accounts.utils.time.time", return_value=1000):
            adjust_session_expiry(request=request, user=self.user, is_login=False)

        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_AUTHENTICATED
        )
        self.assertEqual(request.session[SESSION_EXPIRY_AGE], 1200)
        self.assertEqual(request.session[SESSION_EXPIRY_REFRESHED], 1000)
        self.assertEqual(request.session.get_expiry_age(), 1200)

        request.session.modified = False
        with mock.patch("weblate.accounts.utils.time.time", return_value=1599):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertFalse(request.session.modified)

        with mock.patch("weblate.accounts.utils.time.time", return_value=1600):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertTrue(request.session.modified)
        self.assertEqual(request.session[SESSION_EXPIRY_REFRESHED], 1600)

    @override_settings(SESSION_COOKIE_AGE_AUTHENTICATED=90)
    def test_short_authenticated_session_expiry_refreshes_before_lifetime(self) -> None:
        request = self.get_request()

        self.assertEqual(get_session_expiry_refresh_seconds(1), 0)
        self.assertLess(get_session_expiry_refresh_seconds(90), 90)

        with mock.patch("weblate.accounts.utils.time.time", return_value=1000):
            adjust_session_expiry(request=request, user=self.user, is_login=False)

        request.session.modified = False
        with mock.patch("weblate.accounts.utils.time.time", return_value=1029):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertFalse(request.session.modified)

        with mock.patch("weblate.accounts.utils.time.time", return_value=1030):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertTrue(request.session.modified)
        self.assertEqual(request.session[SESSION_EXPIRY_REFRESHED], 1030)

    @override_settings(
        SESSION_COOKIE_AGE=1000,
        SESSION_COOKIE_AGE_2FA=180,
        SESSION_COOKIE_AGE_AUTHENTICATED=1200,
    )
    def test_session_expiry_scope_changes(self) -> None:
        request = self.get_request()

        with mock.patch("weblate.accounts.utils.time.time", return_value=1000):
            adjust_session_expiry(request=request, user=self.user)
        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_LOGIN
        )
        self.assertEqual(request.session.get_expiry_age(), 1000)

        request.session.modified = False
        with mock.patch("weblate.accounts.utils.time.time", return_value=1001):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertTrue(request.session.modified)
        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_AUTHENTICATED
        )
        self.assertEqual(request.session.get_expiry_age(), 1200)

    @override_settings(
        SESSION_COOKIE_AGE_2FA=180, SESSION_COOKIE_AGE_AUTHENTICATED=1200
    )
    def test_second_factor_session_promotes_to_authenticated(self) -> None:
        request = self.get_request()
        TOTPDevice.objects.create(user=self.user)

        with mock.patch("weblate.accounts.utils.time.time", return_value=1000):
            adjust_session_expiry(request=request, user=self.user)
        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_2FA
        )
        self.assertEqual(request.session.get_expiry_age(), 180)

        request.session[DEVICE_ID_SESSION_KEY] = "otp_totp.totpdevice/1"
        request.session.modified = False
        with mock.patch("weblate.accounts.utils.time.time", return_value=1001):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertTrue(request.session.modified)
        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_AUTHENTICATED
        )
        self.assertEqual(request.session.get_expiry_age(), 1200)

    def test_saml_session_expiry_is_not_refreshed(self) -> None:
        request = self.get_request({"next": "/idp/login/process/"})

        with mock.patch("weblate.accounts.utils.time.time", return_value=1000):
            adjust_session_expiry(request=request, user=self.user)
        self.assertTrue(request.session["saml_only"])
        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_SAML
        )
        self.assertEqual(request.session.get_expiry_age(), 60)

        request.session.modified = False
        with mock.patch("weblate.accounts.utils.time.time", return_value=10_000):
            adjust_session_expiry(request=request, user=self.user, is_login=False)
        self.assertFalse(request.session.modified)

    def test_saml_second_factor_session_stays_short_after_completion(self) -> None:
        request = self.get_request({"next": "/idp/login/process/"})
        TOTPDevice.objects.create(user=self.user)

        with mock.patch("weblate.accounts.utils.time.time", return_value=1000):
            adjust_session_expiry(request=request, user=self.user)
        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_SAML
        )

        request.session[DEVICE_ID_SESSION_KEY] = "otp_totp.totpdevice/1"
        with mock.patch("weblate.accounts.utils.time.time", return_value=1001):
            adjust_session_expiry(
                request=request,
                user=self.user,
                is_login=False,
                force=True,
            )

        self.assertEqual(
            request.session[SESSION_EXPIRY_SCOPE], SESSION_EXPIRY_SCOPE_SAML
        )
        self.assertEqual(request.session.get_expiry_age(), 60)


class TasksTest(TestCase):
    def test_cleanup_social_auth(self) -> None:
        cleanup_social_auth()

    def test_cleanup_auditlog(self) -> None:
        cleanup_auditlog()


@override_settings(
    PRIVATE_COMMIT_EMAIL_TEMPLATE="{username}@users.noreply.{site_domain}",
    SITE_DOMAIN="example.com",
    SITE_TITLE="Weblate",
)
class FormatPrivateMainTestCase(SimpleTestCase):
    def validate_email(self, username: str, expected: str) -> None:
        # Make sure username is valid
        if username:
            validate_username(username)
        # Generate e-mail
        email = format_private_commit_data(
            settings.PRIVATE_COMMIT_EMAIL_TEMPLATE, username, 99
        )

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
