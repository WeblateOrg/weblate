# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

from __future__ import annotations

from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils.timezone import now
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.models import WebAuthnCredential

from weblate.accounts.models import AuditLog
from weblate.accounts.tasks import cleanup_auditlog
from weblate.accounts.utils import SESSION_WEBAUTHN_AUDIT
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

    def assert_audit_mail(self) -> None:
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject, "[Weblate] Activity on your account at Weblate"
        )
        mail.outbox.clear()

    def test_audit_maturing(self) -> None:
        audit = self.create_webauthn_audit()
        audit.timestamp = now() - timedelta(minutes=10)
        audit.save()
        self.assertEqual(len(mail.outbox), 0)
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
        response = self.client.post(url, {"name": test_name}, follow=True)
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
        response = self.client.post(url, {"delete": ""}, follow=True)
        self.assertEqual(WebAuthnCredential.objects.all().count(), 0)
        # The audit log for removal should be present
        self.assertContains(response, test_name)
        self.assert_audit_mail()

    def add_totp(self, test_name: str = "test totp name"):
        # Display form to get TOTP params
        response = self.client.get(reverse("totp"))

        # Generate TOTP response
        totp_key = response.context["form"].bin_key
        totp_response = totp(totp_key, 30, 0, 6, 0)

        # Register TOTP device
        response = self.client.post(
            reverse("totp"), {"name": test_name, "token": totp_response}, follow=True
        )
        self.assertContains(response, test_name)
        devices = TOTPDevice.objects.all()
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assert_audit_mail()
        return device

    def test_totp(self) -> None:
        test_name = "test totp name"

        device = self.add_totp(test_name)

        # Remove it
        response = self.client.post(
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

        # We should be on 2fa page without an user set now
        self.assertNotEqual(response.context["user"], self.user)

        totp_response = totp(
            device.bin_key, device.step, device.t0, device.digits, device.drift
        )

        response = self.client.post(expected_url, {"otp_token": "000000"})
        self.assertNotEqual(response.context["user"], self.user)

        response = self.client.post(
            expected_url, {"otp_token": totp_response}, follow=True
        )
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
