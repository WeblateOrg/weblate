# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING, Never
from unittest import mock

from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.exceptions import OTPWebAuthnApiError
from django_otp_webauthn.views import CompleteCredentialAuthenticationView
from rest_framework.authtoken.models import Token

from weblate.accounts.forms import LoginForm, TOTPTokenForm
from weblate.accounts.models import AuditLog
from weblate.accounts.utils import (
    SESSION_SECOND_FACTOR_USER,
    set_second_factor_session,
)
from weblate.auth.models import User

if TYPE_CHECKING:
    from collections.abc import Callable


@override_settings(AUTH_LOCK_ATTEMPTS=1)
class AuthenticationLockoutTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user(
            "lockout-user", "lockout@example.com", password="test-password"
        )
        self.api_key = Token.objects.get(user=self.user).key
        self.first_verifying = Event()
        self.second_locking = Event()
        self.enterContext(mock.patch("weblate.accounts.models.notify_auditlog.delay"))

    def hold_verification(self) -> None:
        self.first_verifying.set()
        self.assertTrue(self.second_locking.wait(timeout=10))

    def run_overlapping[T, U](
        self, first: Callable[[], T], second: Callable[[], U]
    ) -> tuple[T, U]:
        def observe_lock(
            execute: Callable[..., object],
            sql: str,
            params: object,
            many: bool,
            context: dict[str, object],
        ) -> object:
            if "FOR UPDATE" in sql and "weblate_auth_user" in sql:
                self.second_locking.set()
            return execute(sql, params, many, context)

        def run_first() -> T:
            close_old_connections()
            try:
                return first()
            finally:
                connection.close()

        def run_second() -> U:
            close_old_connections()
            try:
                with connection.execute_wrapper(observe_lock):
                    return second()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_result = executor.submit(run_first)
            self.assertTrue(self.first_verifying.wait(timeout=10))
            second_result = executor.submit(run_second)
            return first_result.result(timeout=20), second_result.result(timeout=20)

    def assert_locked_once(self) -> None:
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(
            AuditLog.objects.filter(user=self.user, activity="locked").count(), 1
        )
        self.assertEqual(Token.objects.get(user=self.user).key, self.api_key)

    def test_username_and_email_are_serialized(self) -> None:
        checked_passwords = []

        def reject_password(user: User, _password: str) -> bool:
            checked_passwords.append(user.password)
            if user.has_usable_password():
                self.hold_verification()
            return False

        def submit(identifier: str) -> User | None:
            request = RequestFactory().post(reverse("login"))
            return LoginForm(request).authenticate_account(identifier, "unused")

        old_password = self.user.password
        with mock.patch.object(User, "check_password", autospec=True) as verify:
            verify.side_effect = reject_password
            result = self.run_overlapping(
                lambda: submit(self.user.username), lambda: submit(self.user.email)
            )

        self.assertEqual(result, (None, None))
        self.assert_locked_once()
        self.assertEqual(checked_passwords, [old_password, self.user.password])

    def test_webauthn_lockout_invalidates_waiting_totp_session(self) -> None:
        TOTPDevice.objects.create(user=self.user, confirmed=True)
        webauthn_client, totp_client = Client(), Client()
        for client in (webauthn_client, totp_client):
            request = RequestFactory().post("/")
            request.session = client.session
            set_second_factor_session(
                request,
                self.user,
                "weblate.accounts.auth.WeblateUserBackend",
            )
            request.session.save()

        def reject_assertion(*args: object, **kwargs: object) -> Never:
            self.hold_verification()
            msg = "Invalid credential"
            raise OTPWebAuthnApiError(msg, "invalid_credential")

        with (
            mock.patch.object(
                CompleteCredentialAuthenticationView,
                "post",
                side_effect=reject_assertion,
            ),
            mock.patch.object(TOTPTokenForm, "_verify_token") as verify_totp,
        ):
            webauthn, totp = self.run_overlapping(
                lambda: webauthn_client.post(
                    reverse("otp_webauthn:credential-authentication-complete"),
                    {},
                    content_type="application/json",
                    REMOTE_ADDR="192.0.2.31",
                ),
                lambda: totp_client.post(
                    reverse("2fa-login", kwargs={"backend": "totp"}),
                    {"otp_token": "000000"},
                    REMOTE_ADDR="192.0.2.32",
                ),
            )

        self.assertEqual(webauthn.status_code, 403)
        self.assertEqual(webauthn.json()["code"], "account_locked")
        self.assertEqual(totp.status_code, 404)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, totp_client.session)
        verify_totp.assert_not_called()
        self.assertEqual(
            AuditLog.objects.get(user=self.user, activity="twofactor-failed").params,
            {"device_type": "webauthn"},
        )
        self.assert_locked_once()
