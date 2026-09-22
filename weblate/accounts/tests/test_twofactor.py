# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.exceptions import OTPWebAuthnApiError
from django_otp_webauthn.models import WebAuthnCredential
from rest_framework.authtoken.models import Token

from weblate.accounts.models import AuditLog
from weblate.accounts.pipeline import second_factor
from weblate.accounts.tasks import cleanup_auditlog
from weblate.accounts.utils import (
    SECOND_FACTOR_VERIFY_SECONDS,
    SESSION_SECOND_FACTOR_HASH,
    SESSION_SECOND_FACTOR_SOCIAL,
    SESSION_SECOND_FACTOR_TIMESTAMP,
    SESSION_SECOND_FACTOR_USER,
    SESSION_WEBAUTHN_AUDIT,
)
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.ratelimit import reset_rate_limit


class TwoFactorTestCase(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        reset_rate_limit("login", address="127.0.0.1")

    def test_recovery_codes(self) -> None:
        user = self.user
        response = self.client.get(reverse("recovery-codes"))
        self.assertContains(response, "Recovery codes")
        self.assertFalse(StaticDevice.objects.filter(user=user).exists())

        response = self.client.post(reverse("recovery-codes"), follow=True)
        self.assertContains(response, "Recovery codes")
        self.assertTrue(StaticDevice.objects.filter(user=user).exists())
        self.assertTrue(StaticToken.objects.filter(device__user=user).exists())

        code = StaticToken.objects.filter(device__user=user).first().token

        self.assertContains(response, code)

    def create_webauthn_audit(self):
        return AuditLog.objects.create(
            self.user, None, "twofactor-add", device="", skip_notify=True
        )

    def assert_audit_mail(self, *, expected: int = 1) -> None:
        self.assertEqual(len(mail.outbox), expected)
        self.assertEqual(
            mail.outbox[0].subject, "[Weblate] Activity on your account at Weblate"
        )
        mail.outbox.clear()

    def post_with_callbacks(self, *args, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(*args, **kwargs)

    def test_audit_maturing(self) -> None:
        audit = self.create_webauthn_audit()
        audit.timestamp = now() - timedelta(minutes=10)
        audit.save()
        self.assertEqual(len(mail.outbox), 0)
        with self.captureOnCommitCallbacks(execute=True):
            cleanup_auditlog()
        self.assert_audit_mail()

    def test_webauthn(self) -> None:
        user = self.user
        test_name = "test webauthn name"
        credential = WebAuthnCredential.objects.create(user=user)

        url = reverse("webauthn-detail", kwargs={"pk": credential.pk})

        # Mock what weblate.accounts.utils.WeblateWebAuthnHelper does
        audit = self.create_webauthn_audit()
        session = self.client.session
        session.update({SESSION_WEBAUTHN_AUDIT: audit.pk})
        session.save()
        self.assertEqual(len(mail.outbox), 0)

        # Test initial naming
        response = self.post_with_callbacks(url, {"name": test_name}, follow=True)
        # The device should be listed
        self.assertContains(response, test_name)
        # Audit log mail should be triggered
        self.assert_audit_mail()
        # The audit log should be updated
        audit.refresh_from_db()
        self.assertEqual(audit.params, {"device": test_name})

        # Test naming
        response = self.client.post(url, {"name": test_name}, follow=True)
        # The device should be listed
        self.assertContains(response, test_name)

        # The name should be updated
        credential.refresh_from_db()
        self.assertEqual(credential.name, test_name)

        # Test removal
        response = self.post_with_callbacks(url, {"delete": ""}, follow=True)
        self.assertEqual(WebAuthnCredential.objects.all().count(), 0)
        # The audit log for removal should be present
        self.assertContains(response, test_name)
        self.assert_audit_mail()

    def add_totp(
        self,
        test_name: str = "test totp name",
        *,
        expected: int = 1,
        expected_mail: int = 1,
        remove_previous: str = "",
    ):
        # Display form to get TOTP params
        response = self.client.get(reverse("totp"))

        # Generate TOTP response
        device = response.context["form"].device
        # Enroll in the previous timestep so login tests can use the current one.
        timestamp = now().timestamp() - device.step
        with (
            mock.patch("django_otp.oath.time", return_value=timestamp),
            mock.patch("time.time", return_value=timestamp),
        ):
            totp_response = f"{totp(device.bin_key):06d}"
            response = self.post_with_callbacks(
                reverse("totp"),
                {
                    "enrollment": device.pk,
                    "name": test_name,
                    "token": totp_response,
                    "remove_previous": remove_previous,
                },
                follow=True,
            )
        self.assertContains(response, test_name)
        devices = TOTPDevice.objects.all()
        self.assertEqual(len(devices), expected)
        device = devices[0]
        self.assert_audit_mail(expected=expected_mail)
        return device

    def create_totp_device(self) -> TOTPDevice:
        return TOTPDevice.objects.create(
            user=self.user, name="test totp name", confirmed=True
        )

    def start_second_factor_login(
        self, client: Client | None = None, *, address: str = "127.0.0.1"
    ) -> tuple[Client, str]:
        if client is None:
            client = self.client
        client.logout()
        response = client.post(
            reverse("login"),
            {"username": "testuser", "password": "testpassword"},
            REMOTE_ADDR=address,
        )
        second_factor_url = reverse("2fa-login", kwargs={"backend": "totp"})
        self.assertRedirects(response, second_factor_url)
        return client, second_factor_url

    def test_manage_totp(self) -> None:
        self.add_totp("TOTP 1")
        self.add_totp("TOTP 2", expected=2)
        self.assertEqual(
            set(self.user.totpdevice_set.values_list("name", flat=True)),
            {"TOTP 1", "TOTP 2"},
        )
        self.add_totp("TOTP 3", remove_previous="1", expected_mail=3)
        self.assertEqual(
            set(self.user.totpdevice_set.values_list("name", flat=True)), {"TOTP 3"}
        )

    def test_totp(self) -> None:
        test_name = "test totp name"

        device = self.add_totp(test_name)

        # Remove it
        response = self.post_with_callbacks(
            reverse("totp-detail", kwargs={"pk": device.pk}),
            {"delete": "1"},
            follow=True,
        )
        self.assertContains(response, test_name)
        self.assertFalse(TOTPDevice.objects.all().exists())
        self.assert_audit_mail()

    def test_login_plain(self) -> None:
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "testpassword"},
            follow=True,
        )
        self.assertEqual(response.context["user"], self.user)

    def test_login_totp(self) -> None:
        device = self.add_totp()
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "testpassword"},
            follow=True,
        )

        expected_url = reverse("2fa-login", kwargs={"backend": "totp"})
        self.assertRedirects(response, expected_url)

        # We should be on 2fa page without a user set now
        self.assertNotEqual(response.context["user"], self.user)

        totp_response = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"

        response = self.client.post(
            expected_url, {"otp_token": totp_response}, follow=True
        )
        self.assertEqual(response.context["user"], self.user)
        self.assertEqual(
            self.client.session.get_expiry_age(),
            settings.SESSION_COOKIE_AGE_AUTHENTICATED,
        )

    def test_login_totp_leading_zeroes(self) -> None:
        timestamp = int(now().timestamp())
        device = TOTPDevice.objects.create(
            user=self.user,
            name="zero code",
            confirmed=True,
            key="00000000000000000000000000000000003c6643",
            step=300,
            t0=timestamp,
            tolerance=0,
        )
        self.assertEqual(
            totp(device.bin_key, device.step, device.t0, device.digits, device.drift),
            0,
        )
        client, second_factor_url = self.start_second_factor_login()

        response = client.post(second_factor_url, {"otp_token": "000000"}, follow=True)

        self.assertEqual(response.context["user"], self.user)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, client.session)
        self.assertNotIn(SESSION_SECOND_FACTOR_HASH, client.session)

    @override_settings(AUTH_LOCK_ATTEMPTS=10, RATELIMIT_ATTEMPTS=20)
    def test_login_totp_requires_six_ascii_digits(self) -> None:
        self.create_totp_device()
        client, second_factor_url = self.start_second_factor_login()

        for data in (
            {},
            {"otp_token": "00000"},
            {"otp_token": "0000000"},
            {"otp_token": "abcdef"},
            {"otp_token": "٠٠٠٠٠٠"},
        ):
            response = client.post(second_factor_url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors["otp_token"])

        self.assertEqual(
            AuditLog.objects.filter(
                user=self.user, activity="twofactor-failed"
            ).count(),
            5,
        )

    @override_settings(
        AUTH_LOCK_ATTEMPTS=3,
        OTP_TOTP_THROTTLE_FACTOR=0,
        RATELIMIT_ATTEMPTS=20,
    )
    def test_second_factor_failures_lock_account(self) -> None:
        device = self.create_totp_device()
        old_token = Token.objects.get(user=self.user).key
        clients = []
        for index in range(4):
            client = Client()
            clients.append(
                self.start_second_factor_login(client, address=f"192.0.2.{index + 1}")[
                    0
                ]
            )
        second_factor_url = reverse("2fa-login", kwargs={"backend": "totp"})
        valid_token = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"
        invalid_token = "000000" if valid_token != "000000" else "000001"

        response = clients[0].post(
            second_factor_url,
            {"otp_token": invalid_token},
            REMOTE_ADDR="192.0.2.1",
        )
        self.assertEqual(response.status_code, 200)
        response = clients[1].post(second_factor_url, {}, REMOTE_ADDR="192.0.2.2")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())
        self.assertFalse(
            AuditLog.objects.filter(user=self.user, activity="locked").exists()
        )

        response = clients[2].post(
            second_factor_url,
            {"otp_token": "٠٠٠٠٠٠"},
            REMOTE_ADDR="192.0.2.3",
            follow=True,
        )

        self.assertRedirects(response, reverse("login"))
        self.assertContains(
            response,
            "Too many failed authentication attempts. Please reset your password "
            "to regain access to your account.",
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(Token.objects.get(user=self.user).key, old_token)
        self.assertEqual(
            AuditLog.objects.filter(
                user=self.user, activity="twofactor-failed"
            ).count(),
            3,
        )
        self.assertEqual(
            AuditLog.objects.filter(user=self.user, activity="locked").count(), 1
        )
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, clients[2].session)
        self.assertNotIn(SESSION_SECOND_FACTOR_HASH, clients[2].session)

        response = clients[3].post(
            second_factor_url,
            {"otp_token": valid_token},
            REMOTE_ADDR="192.0.2.4",
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, clients[3].session)

        fresh_client = Client()
        response = fresh_client.post(
            reverse("login"),
            {"username": "testuser", "password": "testpassword"},
            REMOTE_ADDR="192.0.2.5",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, fresh_client.session)

    @override_settings(
        AUTH_LOCK_ATTEMPTS=3,
        OTP_TOTP_THROTTLE_FACTOR=0,
        RATELIMIT_ATTEMPTS=20,
    )
    def test_successful_second_factor_resets_lockout_sequence(self) -> None:
        device = self.create_totp_device()
        client, second_factor_url = self.start_second_factor_login()
        for _unused in range(2):
            response = client.post(second_factor_url, {})
            self.assertEqual(response.status_code, 200)
        valid_token = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"

        response = client.post(
            second_factor_url, {"otp_token": valid_token}, follow=True
        )

        self.assertEqual(response.context["user"], self.user)
        client, second_factor_url = self.start_second_factor_login(client)
        for _unused in range(2):
            response = client.post(second_factor_url, {})
            self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())
        self.assertFalse(
            AuditLog.objects.filter(user=self.user, activity="locked").exists()
        )

    @override_settings(AUTH_LOCK_ATTEMPTS=1, RATELIMIT_ATTEMPTS=20)
    def test_recovery_failure_locks_account(self) -> None:
        self.create_totp_device()
        recovery = StaticDevice.objects.create(
            user=self.user, name="recovery", confirmed=True
        )
        StaticToken.objects.create(device=recovery, token="recovery-code")
        client, _second_factor_url = self.start_second_factor_login()

        response = client.post(
            reverse("2fa-login", kwargs={"backend": "recovery"}),
            {"otp_token": "invalid-code"},
            follow=True,
        )

        self.assertRedirects(response, reverse("login"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    @override_settings(AUTH_LOCK_ATTEMPTS=1, RATELIMIT_ATTEMPTS=20)
    def test_webauthn_failure_returns_account_locked_error(self) -> None:
        self.create_totp_device()
        client, _second_factor_url = self.start_second_factor_login()

        with mock.patch(
            "django_otp_webauthn.views.CompleteCredentialAuthenticationView.post",
            side_effect=OTPWebAuthnApiError("Invalid credential", "invalid_credential"),
        ):
            response = client.post(
                reverse("otp_webauthn:credential-authentication-complete"),
                data={},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Too many failed authentication attempts. Please reset your "
                    "password to regain access to your account."
                ),
                "code": "account_locked",
            },
        )
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, client.session)

    def test_pending_second_factor_requires_auth_hash(self) -> None:
        self.create_totp_device()
        client, second_factor_url = self.start_second_factor_login()
        session = client.session
        session.pop(SESSION_SECOND_FACTOR_HASH)
        session.save()

        response = client.get(second_factor_url)

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, client.session)

    def test_password_change_invalidates_pending_second_factor(self) -> None:
        self.create_totp_device()
        client, second_factor_url = self.start_second_factor_login()
        self.user.set_password("changed-password")
        self.user.save(update_fields=["password"])

        response = client.get(second_factor_url)

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, client.session)

    def test_social_second_factor_stores_auth_hash(self) -> None:
        self.create_totp_device()
        strategy = SimpleNamespace(request=SimpleNamespace(session={}))

        response = second_factor.__wrapped__(
            strategy=strategy,
            backend=SimpleNamespace(name="github"),
            user=self.user,
            current_partial=SimpleNamespace(token="partial-token"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            strategy.request.session[SESSION_SECOND_FACTOR_HASH],
            self.user.get_session_auth_hash(),
        )
        self.assertEqual(
            strategy.request.session[SESSION_SECOND_FACTOR_USER], (self.user.id, "")
        )
        self.assertTrue(strategy.request.session[SESSION_SECOND_FACTOR_SOCIAL])

    def test_login_totp_saml_expiry(self) -> None:
        device = self.add_totp()
        self.client.logout()
        response = self.client.post(
            reverse("login"),
            {
                "username": "testuser",
                "password": "testpassword",
                "next": "/idp/login/process/",
            },
        )

        second_factor_url = response["Location"]
        totp_response = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"
        response = self.client.post(second_factor_url, {"otp_token": totp_response})

        self.assertRedirects(
            response, "/idp/login/process/", fetch_redirect_response=False
        )
        self.assertEqual(self.client.session.get_expiry_age(), 60)

    def test_login_totp_rejects_unsafe_next(self) -> None:
        device = self.add_totp()
        self.client.logout()

        response = self.client.post(
            reverse("login"),
            {
                "username": "testuser",
                "password": "testpassword",
                "next": "https://evil.example/",
            },
        )

        second_factor_url = response["Location"]
        self.assertTrue(
            second_factor_url.startswith(
                reverse("2fa-login", kwargs={"backend": "totp"})
            )
        )
        self.assertIn("next=https%3A%2F%2Fevil.example%2F", second_factor_url)

        totp_response = f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"
        response = self.client.post(
            second_factor_url, {"otp_token": totp_response}, follow=True
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(response.context["user"], self.user)

    def test_team_enforced_2fa(self) -> None:
        # Turn on enforcement on all user teams
        self.user.groups.update(enforced_2fa=True)
        url = self.project.get_absolute_url()

        # Access without second factor
        response = self.client.get(url)
        # Not found because user doesn't have access to the project
        self.assertEqual(response.status_code, 404)

        # Configure second factor
        self.test_login_totp()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_password_requires_recent_second_factor(self) -> None:
        self.add_totp()

        with mock.patch("weblate.accounts.views.time.time") as mocked_time:
            mocked_time.return_value = 2_000_000_000

            stale_session = self.client.session
            stale_session[SESSION_SECOND_FACTOR_TIMESTAMP] = int(
                mocked_time.return_value
            ) - (SECOND_FACTOR_VERIFY_SECONDS + 1)
            stale_session.save()

            response = self.client.get(reverse("password"))

        self.assertRedirects(
            response,
            f"{reverse('2fa-login', kwargs={'backend': 'totp'})}?next={reverse('password')}",
        )
        self.assertEqual(
            self.client.session[SESSION_SECOND_FACTOR_HASH],
            self.user.get_session_auth_hash(),
        )

    def test_password_allows_recent_second_factor(self) -> None:
        self.add_totp()

        with mock.patch("weblate.accounts.views.time.time") as mocked_time:
            mocked_time.return_value = 2_000_000_000

            session = self.client.session
            session[SESSION_SECOND_FACTOR_TIMESTAMP] = (
                int(mocked_time.return_value) - SECOND_FACTOR_VERIFY_SECONDS
            )
            session.save()

            response = self.client.get(reverse("password"))

        self.assertContains(response, "Current password")

    def test_project_enforced_2fa(self) -> None:
        # Turn on enforcement on project and make user an admin
        self.project.add_user(self.user, "Administration")
        self.project.enforced_2fa = True
        self.project.save()

        url = reverse("git_status", kwargs={"path": self.project.get_url_path()})

        # Access without second factor
        response = self.client.get(url)
        # Permission denied because user still has access to the project
        self.assertEqual(response.status_code, 403)

        # Configure second factor
        self.test_login_totp()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
