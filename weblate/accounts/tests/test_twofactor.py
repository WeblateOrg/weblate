# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from django.http import HttpResponseRedirect
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.exceptions import OTPWebAuthnApiError
from django_otp_webauthn.helpers import WebAuthnHelper
from django_otp_webauthn.models import WebAuthnCredential
from rest_framework.authtoken.models import Token
from social_core.exceptions import AuthSessionError

from weblate.accounts.models import AuditLog
from weblate.accounts.pipeline import (
    second_factor,
    verify_first_factor_sso,
    verify_recent_second_factor,
)
from weblate.accounts.tasks import cleanup_auditlog
from weblate.accounts.utils import (
    SECOND_FACTOR_VERIFY_SECONDS,
    SESSION_FIRST_FACTOR_GRANT,
    SESSION_FIRST_FACTOR_SSO,
    SESSION_FIRST_WEBAUTHN_NAME,
    SESSION_SECOND_FACTOR_HASH,
    SESSION_SECOND_FACTOR_SOCIAL,
    SESSION_SECOND_FACTOR_TIMESTAMP,
    SESSION_SECOND_FACTOR_USER,
    SESSION_WEBAUTHN_AUDIT,
    has_first_factor_grant,
    has_recent_second_factor,
)
from weblate.auth.models import User
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.ratelimit import reset_rate_limit

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class TwoFactorTestCase(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        reset_rate_limit("login", address="127.0.0.1")

    def test_webauthn_registration_page(self) -> None:
        url = reverse("webauthn-register")
        self.assertRedirects(
            self.client.get(url),
            f"{reverse('first-factor-verify')}?target=webauthn",
            fetch_redirect_response=False,
        )
        self.confirm_first_factor("webauthn")
        response = self.client.get(url)
        self.assertContains(response, "Register new security key")
        self.assertContains(response, 'id="passkey-registration-placeholder"')
        self.assertContains(
            response, reverse("webauthn-detail", kwargs={"pk": "000000"})
        )

        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_first_webauthn_registration_allows_naming(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.assertFalse(self.user.has_perm("project.edit", self.project))
        self.confirm_first_factor("webauthn")
        with (
            mock.patch.object(
                WebAuthnHelper,
                "register_begin",
                return_value=({}, {"challenge": "test"}),
            ),
            mock.patch.object(
                WebAuthnHelper,
                "register_complete",
                side_effect=lambda user, _state, _data: (
                    WebAuthnCredential.objects.create(user=user)
                ),
            ),
        ):
            begin_response = self.client.post(
                reverse("otp_webauthn:credential-registration-begin"),
                data="{}",
                content_type="application/json",
            )
            self.assertEqual(begin_response.status_code, 200)
            complete_response = self.client.post(
                reverse("otp_webauthn:credential-registration-complete"),
                data="{}",
                content_type="application/json",
            )

        self.assertEqual(complete_response.status_code, 200)
        credential = WebAuthnCredential.objects.get(pk=complete_response.json()["id"])
        session = self.client.session
        self.assertNotIn(SESSION_SECOND_FACTOR_TIMESTAMP, session)
        self.assertNotIn(SESSION_FIRST_FACTOR_GRANT, session)
        self.assertIn(SESSION_FIRST_WEBAUTHN_NAME, session)
        self.assertTrue(
            User.objects.get(pk=self.user.pk).has_perm("project.edit", self.project)
        )
        token_count = Token.objects.count()
        token_response = self.client.post(
            reverse("create-project-token", kwargs={"project": self.project.slug}),
            {"full_name": "Unauthorized token", "date_expires": "2999-12-31"},
        )
        self.assertEqual(token_response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "webauthn"}),
            token_response["Location"],
        )
        self.assertEqual(Token.objects.count(), token_count)
        audit = AuditLog.objects.get(pk=session[SESSION_WEBAUTHN_AUDIT])

        detail_url = reverse("webauthn-detail", kwargs={"pk": credential.pk})
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "webauthn"}),
            self.client.post(detail_url, {"delete": "1"})["Location"],
        )
        self.assertTrue(WebAuthnCredential.objects.filter(pk=credential.pk).exists())

        response = self.client.post(
            reverse("webauthn-detail", kwargs={"pk": credential.pk}),
            {"name": "My security key"},
        )
        self.assertEqual(response.status_code, 302)
        credential.refresh_from_db()
        audit.refresh_from_db()
        self.assertEqual(credential.name, "My security key")
        self.assertEqual(audit.params, {"device": "My security key"})
        self.assertNotIn(SESSION_FIRST_WEBAUTHN_NAME, self.client.session)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "webauthn"}),
            self.client.post(detail_url, {"name": "Again"})["Location"],
        )

    def test_first_factor_requires_existing_password(self) -> None:
        totp_url = reverse("totp")
        verify_url = reverse("first-factor-verify")
        self.assertRedirects(
            self.client.get(totp_url),
            f"{verify_url}?target=totp",
            fetch_redirect_response=False,
        )
        for name in (
            "otp_webauthn:credential-registration-begin",
            "otp_webauthn:credential-registration-complete",
        ):
            response = self.client.post(
                reverse(name), data="{}", content_type="application/json"
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.json()["code"], "first_factor_verification_required"
            )
        response = self.client.post(
            verify_url, {"target": "totp", "password": "incorrect"}
        )
        self.assertContains(response, "You have entered an invalid password.")
        self.assertNotIn(SESSION_FIRST_FACTOR_GRANT, self.client.session)
        session = self.client.session
        session["otp_webauthn_register_state"] = {"challenge": "stale"}
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = int(time.time())
        session.save()
        old_session_key = self.client.session.session_key
        self.confirm_first_factor()
        self.assertNotEqual(self.client.session.session_key, old_session_key)
        self.assertNotIn("otp_webauthn_register_state", self.client.session)
        self.assertNotIn(SESSION_SECOND_FACTOR_TIMESTAMP, self.client.session)
        self.assertNotIn(
            SESSION_FIRST_FACTOR_GRANT, SessionStore(session_key=old_session_key).load()
        )
        self.assertEqual(self.client.get(totp_url).status_code, 200)

        session = self.client.session
        grant = session[SESSION_FIRST_FACTOR_GRANT]
        grant["time"] -= 601
        session[SESSION_FIRST_FACTOR_GRANT] = grant
        session.save()
        self.assertEqual(self.client.get(totp_url).status_code, 302)

    def test_first_totp_does_not_authorize_project_token(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.project.enforced_2fa = True
        self.project.save(update_fields=["enforced_2fa"])
        self.assertFalse(self.user.has_perm("project.edit", self.project))

        self.confirm_first_factor()
        response = self.client.get(reverse("totp"))
        device = response.context["form"].device
        response = self.client.post(
            reverse("totp"),
            {
                "enrollment": device.pk,
                "name": "First app",
                "token": f"{totp(device.bin_key):06d}",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            User.objects.get(pk=self.user.pk).has_perm("project.edit", self.project)
        )
        self.assertNotIn(SESSION_SECOND_FACTOR_TIMESTAMP, self.client.session)
        token_count = Token.objects.count()
        response = self.client.post(
            reverse("create-project-token", kwargs={"project": self.project.slug}),
            {"full_name": "Unauthorized token", "date_expires": "2999-12-31"},
        )
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}),
            response["Location"],
        )
        self.assertEqual(Token.objects.count(), token_count)

    def test_passwordless_sso_requires_same_linked_identity(self) -> None:
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.client.force_login(self.user)
        association = self.user.social_auth.create(provider="github", uid="owner")
        with (
            mock.patch("weblate.accounts.views.get_auth_keys", return_value={"github"}),
            mock.patch(
                "weblate.accounts.views.social_auth",
                return_value=HttpResponseRedirect("/provider/"),
            ),
        ):
            response = self.client.post(
                reverse("first-factor-verify"),
                {"target": "totp", "association": association.pk},
            )
        self.assertEqual(response["Location"], "/provider/")

        request = self.factory.get(reverse("first-factor-verify"))
        request.user = self.user
        request.session = self.client.session
        backend = SimpleNamespace(name="github")
        other_user = User.objects.create_user("other-sso", "other@example.com")
        other_association = other_user.social_auth.create(
            provider="github", uid="other"
        )
        with self.assertRaises(AuthSessionError):
            verify_first_factor_sso(
                SimpleNamespace(request=request), backend, other_user, other_association
            )
        self.assertFalse(
            has_first_factor_grant(cast("AuthenticatedHttpRequest", request))
        )

        request.session[SESSION_FIRST_FACTOR_SSO] = self.client.session[
            SESSION_FIRST_FACTOR_SSO
        ]
        old_session_key = request.session.session_key
        result = verify_first_factor_sso(
            SimpleNamespace(request=request), backend, self.user, association
        )
        self.assertEqual(result.url, reverse("totp"))
        self.assertNotEqual(request.session.session_key, old_session_key)
        self.assertTrue(
            has_first_factor_grant(cast("AuthenticatedHttpRequest", request))
        )

    def test_passwordless_without_provider_cannot_enroll(self) -> None:
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("first-factor-verify"))
        self.assertContains(response, "Contact an administrator to recover access")
        response = self.client.post(
            reverse("first-factor-verify"),
            {"target": "totp", "association": "1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SESSION_FIRST_FACTOR_GRANT, self.client.session)

    def confirm_first_factor(self, target: str = "totp") -> None:
        response = self.client.post(
            reverse("first-factor-verify"),
            {"target": target, "password": "testpassword"},
        )
        self.assertRedirects(
            response,
            reverse("totp" if target == "totp" else "webauthn-register"),
            fetch_redirect_response=False,
        )

    def test_recovery_codes(self) -> None:
        user = self.user
        response = self.client.get(reverse("recovery-codes"))
        self.assertContains(response, "Recovery codes")
        self.assertNotContains(response, "Your old codes will become invalid")
        self.assertFalse(StaticDevice.objects.filter(user=user).exists())

        response = self.client.post(reverse("recovery-codes"), follow=True)
        self.assertContains(response, "Recovery codes")
        self.assertTrue(StaticDevice.objects.filter(user=user).exists())
        self.assertTrue(StaticToken.objects.filter(device__user=user).exists())

        code = StaticToken.objects.filter(device__user=user).first().token

        self.assertContains(response, code)
        self.assertContains(response, "Your old codes will become invalid")

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
        self.mark_recent_second_factor()

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
        if self.user.profile.has_2fa:
            self.mark_recent_second_factor()
        else:
            self.confirm_first_factor()
        # Display form to get TOTP params
        response = self.client.get(reverse("totp"))

        # Generate TOTP response
        device = response.context["form"].device
        # Enroll in the previous timestep so login tests can use the current one.
        timestamp = now().timestamp() - device.step
        with (
            mock.patch("django_otp.oath.time", return_value=timestamp),
            mock.patch(
                "django_otp.plugins.otp_totp.models.time",
                time=mock.Mock(return_value=timestamp),
            ),
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
        self.mark_recent_second_factor()
        return device

    def mark_recent_second_factor(self) -> None:
        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()),
        }
        session.save()

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

    def test_login_totp_single_device_has_no_selector(self) -> None:
        device = self.create_totp_device()
        client, url = self.start_second_factor_login()

        response = client.get(url)
        self.assertNotContains(response, 'name="otp_device"')
        self.assertNotIn("otp_device", response.context["form"].fields)

        token = f"{totp(device.bin_key):06d}"
        response = client.post(url, {"otp_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SESSION_SECOND_FACTOR_USER, client.session)

    def test_login_totp_multiple_devices_requires_selection(self) -> None:
        first = self.create_totp_device()
        second = TOTPDevice.objects.create(
            user=self.user, name="second app", confirmed=True
        )
        client, url = self.start_second_factor_login()
        token = f"{totp(second.bin_key):06d}"

        response = client.get(url)
        self.assertContains(response, 'name="otp_device"')
        self.assertEqual(
            list(response.context["form"].fields["otp_device"].choices),
            [
                ("", "---------"),
                (first.persistent_id, f"{first.name} (#{first.pk})"),
                (second.persistent_id, f"{second.name} (#{second.pk})"),
            ],
        )
        for choice in (None, ""):
            data = {"otp_token": token}
            if choice is not None:
                data["otp_device"] = choice
            response = client.post(url, data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("otp_device", response.context["form"].errors)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.throttling_failure_count, 0)
        self.assertEqual(second.throttling_failure_count, 0)

        response = client.post(
            url, {"otp_device": second.persistent_id, "otp_token": token}
        )
        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.throttling_failure_count, 0)

        client, url = self.start_second_factor_login(client)
        response = client.post(
            url,
            {
                "otp_device": first.persistent_id,
                "otp_token": f"{totp(first.bin_key):06d}",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_totp_labels_distinguish_duplicate_and_blank_names(self) -> None:
        first = TOTPDevice.objects.create(
            user=self.user, name="same app", confirmed=True
        )
        second = TOTPDevice.objects.create(
            user=self.user, name="same app", confirmed=True
        )
        blank = TOTPDevice.objects.create(user=self.user, name="", confirmed=True)

        profile = self.client.get(reverse("profile"))
        for label in (
            f"same app (#{first.pk})",
            f"same app (#{second.pk})",
            f"Authentication app (#{blank.pk})",
        ):
            self.assertContains(profile, label)

        client, url = self.start_second_factor_login()
        response = client.get(url)
        self.assertEqual(
            list(response.context["form"].fields["otp_device"].choices),
            [
                ("", "---------"),
                (first.persistent_id, f"same app (#{first.pk})"),
                (second.persistent_id, f"same app (#{second.pk})"),
                (blank.persistent_id, f"Authentication app (#{blank.pk})"),
            ],
        )
        response = client.post(
            url,
            {
                "otp_device": blank.persistent_id,
                "otp_token": f"{totp(blank.bin_key):06d}",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_login_totp_rejects_other_devices_without_verifying(self) -> None:
        first = self.create_totp_device()
        second = TOTPDevice.objects.create(
            user=self.user, name="second app", confirmed=True
        )
        pending = TOTPDevice.objects.create(user=self.user, confirmed=False)
        other = User.objects.create_user("other-totp", "other-totp@example.com")
        foreign = TOTPDevice.objects.create(user=other, confirmed=True)
        recovery = StaticDevice.objects.create(user=self.user)
        client, url = self.start_second_factor_login()
        token = f"{totp(first.bin_key):06d}"

        for device_id in (
            pending.persistent_id,
            foreign.persistent_id,
            recovery.persistent_id,
            "otp_totp.totpdevice/999999999",
        ):
            response = client.post(url, {"otp_device": device_id, "otp_token": token})
            self.assertEqual(response.status_code, 200)
            self.assertIn("otp_device", response.context["form"].errors)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.throttling_failure_count, 0)
        self.assertEqual(second.throttling_failure_count, 0)

    def test_login_totp_removed_selection_is_rejected(self) -> None:
        first = self.create_totp_device()
        second = TOTPDevice.objects.create(
            user=self.user, name="second app", confirmed=True
        )
        client, url = self.start_second_factor_login()
        self.assertContains(client.get(url), 'name="otp_device"')
        second.delete()

        response = client.post(
            url,
            {
                "otp_device": second.persistent_id,
                "otp_token": f"{totp(first.bin_key):06d}",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        first.refresh_from_db()
        self.assertEqual(first.throttling_failure_count, 0)

    def test_login_totp_failure_throttles_only_selected_device(self) -> None:
        first = self.create_totp_device()
        second = TOTPDevice.objects.create(
            user=self.user, name="second app", confirmed=True
        )
        client, url = self.start_second_factor_login()
        valid = {
            totp(device.bin_key, drift=drift)
            for device in (first, second)
            for drift in (-1, 0, 1)
        }
        invalid = next(token for token in range(4) if token not in valid)

        response = client.post(
            url,
            {"otp_device": second.persistent_id, "otp_token": f"{invalid:06d}"},
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.throttling_failure_count, 0)
        self.assertEqual(second.throttling_failure_count, 1)

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

    def test_social_second_factor_rejects_another_users_device(self) -> None:
        self.create_totp_device()
        other_user = User.objects.create_user("other-user", "other@example.org")
        other_device = TOTPDevice.objects.create(user=other_user, confirmed=True)
        own_device = TOTPDevice.objects.get(user=self.user, confirmed=True)
        session = {DEVICE_ID_SESSION_KEY: other_device.persistent_id}
        strategy = SimpleNamespace(request=SimpleNamespace(session=session))
        arguments = {
            "strategy": strategy,
            "backend": SimpleNamespace(name="github"),
            "user": self.user,
            "current_partial": SimpleNamespace(token="partial-token"),
        }

        response = second_factor.__wrapped__(**arguments)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}), response["Location"]
        )
        self.assertNotIn(DEVICE_ID_SESSION_KEY, session)
        self.assertEqual(session[SESSION_SECOND_FACTOR_USER], (self.user.pk, ""))

        session[DEVICE_ID_SESSION_KEY] = own_device.persistent_id
        self.assertIsNone(second_factor.__wrapped__(**arguments))

        session[DEVICE_ID_SESSION_KEY] = "otp_totp.totpdevice/99999999"
        self.assertEqual(second_factor.__wrapped__(**arguments).status_code, 302)
        self.assertNotIn(DEVICE_ID_SESSION_KEY, session)

    def test_new_social_sign_in_clears_unfinished_second_factor(self) -> None:
        device = self.create_totp_device()
        self.client.logout()
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session[SESSION_SECOND_FACTOR_USER] = (self.user.pk, "")
        session[SESSION_SECOND_FACTOR_HASH] = self.user.get_session_auth_hash()
        session[SESSION_SECOND_FACTOR_SOCIAL] = True
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()),
        }
        session.save()

        with mock.patch(
            "weblate.accounts.views.do_auth",
            return_value=HttpResponseRedirect("/provider/"),
        ):
            response = self.client.post(reverse("social:begin", args=("github",)))

        self.assertRedirects(response, "/provider/", fetch_redirect_response=False)
        session = self.client.session
        for key in (
            DEVICE_ID_SESSION_KEY,
            SESSION_SECOND_FACTOR_USER,
            SESSION_SECOND_FACTOR_HASH,
            SESSION_SECOND_FACTOR_SOCIAL,
            SESSION_SECOND_FACTOR_TIMESTAMP,
        ):
            self.assertNotIn(key, session)

    def test_interrupted_social_second_factor_cannot_sign_in_another_user(
        self,
    ) -> None:
        own_device = self.create_totp_device()
        other_user = User.objects.create_user("other-user", "other@example.org")
        TOTPDevice.objects.create(user=other_user, confirmed=True)
        self.client.logout()
        session = self.client.session
        strategy = SimpleNamespace(
            request=SimpleNamespace(user=AnonymousUser(), session=session)
        )
        arguments = {
            "strategy": strategy,
            "backend": SimpleNamespace(name="github"),
            "current_partial": SimpleNamespace(token="partial-token"),
        }
        response = second_factor.__wrapped__(user=self.user, **arguments)
        self.assertEqual(response.status_code, 302)
        session.save()

        code = totp(
            own_device.bin_key,
            own_device.step,
            own_device.t0,
            own_device.digits,
            own_device.drift,
        )
        response = self.client.post(response["Location"], {"otp_token": f"{code:06d}"})
        self.assertEqual(response.status_code, 302)
        session = self.client.session
        self.assertEqual(session[DEVICE_ID_SESSION_KEY], own_device.persistent_id)
        strategy.request.session = session
        self.assertFalse(has_recent_second_factor(strategy.request, user=other_user))

        response = second_factor.__wrapped__(user=other_user, **arguments)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}), response["Location"]
        )
        self.assertNotIn(DEVICE_ID_SESSION_KEY, session)
        self.assertEqual(session[SESSION_SECOND_FACTOR_USER], (other_user.pk, ""))

    def test_recent_second_factor_rejects_another_user(self) -> None:
        device = self.create_totp_device()
        other_user = User.objects.create_user("other-user", "other@example.org")
        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": other_user.pk,
            "time": int(time.time()),
        }
        session.save()
        token = Token.objects.get(user=self.user).key

        self.assertNotIn(token, self.client.get(reverse("profile")).content.decode())
        response = self.client.post(
            reverse("totp-detail", kwargs={"pk": device.pk}), {"delete": "1"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TOTPDevice.objects.filter(pk=device.pk).exists())

        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = int(time.time())
        session.save()
        self.assertNotIn(token, self.client.get(reverse("profile")).content.decode())

        self.mark_recent_second_factor()
        self.assertContains(self.client.get(reverse("profile")), token)

    def test_new_sign_in_method_requires_recent_second_factor(self) -> None:
        self.create_totp_device()
        session: dict[str, object] = {}
        strategy = SimpleNamespace(
            request=SimpleNamespace(user=AnonymousUser(), session=session)
        )
        arguments = {
            "strategy": strategy,
            "backend": SimpleNamespace(name="github"),
            "user": self.user,
            "social": None,
            "weblate_action": "activation",
            "current_partial": SimpleNamespace(token="partial-token"),
        }
        pipeline_step = verify_recent_second_factor.__wrapped__

        response = pipeline_step(**arguments)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}),
            response["Location"],
        )
        self.assertEqual(session[SESSION_SECOND_FACTOR_USER], (self.user.pk, ""))
        self.assertTrue(session[SESSION_SECOND_FACTOR_SOCIAL])

        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()),
        }
        self.assertIsNone(pipeline_step(**arguments))

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

        with mock.patch("weblate.accounts.utils.time") as clock:
            clock.time.return_value = 2_000_000_000

            stale_session = self.client.session
            stale_session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
                "user": self.user.pk,
                "time": int(clock.time.return_value)
                - (SECOND_FACTOR_VERIFY_SECONDS + 1),
            }
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

        with mock.patch("weblate.accounts.utils.time") as clock:
            clock.time.return_value = 2_000_000_000

            session = self.client.session
            session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
                "user": self.user.pk,
                "time": int(clock.time.return_value) - SECOND_FACTOR_VERIFY_SECONDS,
            }
            session.save()

            response = self.client.get(reverse("password"))

        self.assertContains(response, "Current password")

    def test_sensitive_account_views_require_recent_second_factor(self) -> None:
        device = self.create_totp_device()
        recovery = StaticDevice.objects.create(user=self.user, name="Backup Code")
        StaticToken.objects.create(device=recovery, token="secret-code")
        credential = WebAuthnCredential.objects.create(user=self.user)
        old_token = Token.objects.get(user=self.user).key

        for name in (
            "recovery-codes",
            "totp",
            "webauthn-register",
            "email_login",
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(
                    reverse(
                        "2fa-login",
                        kwargs={"backend": self.user.profile.get_second_factor_type()},
                    ),
                    response["Location"],
                )

        response = self.client.post(reverse("recovery-codes"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StaticToken.objects.filter(token="secret-code").exists())
        self.assertFalse(
            TOTPDevice.objects.filter(user=self.user, confirmed=False).exists()
        )

        response = self.client.post(reverse("totp"), {"enrollment": "0"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("email_login"), {"email": "attacker@example.net"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            self.user.social_auth.filter(uid="attacker@example.net").exists()
        )

        association = self.user.social_auth.create(provider="github", uid="attacker")
        response = self.client.post(
            reverse(
                "social:disconnect_individual",
                kwargs={"backend": "github", "association_id": association.pk},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.social_auth.filter(pk=association.pk).exists())

        response = self.client.post(
            reverse("totp-detail", kwargs={"pk": device.pk}), {"delete": "1"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TOTPDevice.objects.filter(pk=device.pk).exists())

        response = self.client.post(
            reverse("webauthn-detail", kwargs={"pk": credential.pk}), {"delete": "1"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WebAuthnCredential.objects.filter(pk=credential.pk).exists())

        response = self.client.post(reverse("reset-api-key"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Token.objects.get(user=self.user).key, old_token)

        for name in (
            "otp_webauthn:credential-registration-begin",
            "otp_webauthn:credential-registration-complete",
        ):
            with self.subTest(name=name):
                response = self.client.post(
                    reverse(name), data="{}", content_type="application/json"
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["code"], "recent_second_factor_required"
                )

        self.mark_recent_second_factor()
        response = self.client.get(reverse("recovery-codes"))
        self.assertContains(response, "secret-code")
        self.assertEqual(self.client.get(reverse("totp")).status_code, 200)
        self.assertEqual(self.client.get(reverse("webauthn-register")).status_code, 200)

    def test_personal_api_key_hidden_until_recent_second_factor(self) -> None:
        self.make_manager()
        token = Token.objects.get(user=self.user).key
        urls = (
            reverse("profile"),
            reverse("data_project", kwargs={"project": self.project.slug}),
            reverse("manage-access", kwargs={"project": self.project.slug}),
        )
        for url in urls:
            with self.subTest(url=url, second_factor=False):
                response = self.client.get(url)
                self.assertNotContains(
                    response, "Verify your identity to view your API key"
                )
                if url != urls[1]:
                    self.assertContains(response, f'data-clipboard-value="{token}"')

        self.create_totp_device()
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(token, response.content.decode())
                self.assertContains(response, reverse("verify-second-factor"))

        self.mark_recent_second_factor()
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, token)
                self.assertNotContains(
                    response, "Verify your identity to view your API key"
                )
                if url != urls[1]:
                    self.assertContains(response, f'data-clipboard-value="{token}"')

        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()) - SECOND_FACTOR_VERIFY_SECONDS - 1,
        }
        session.save()
        self.assertNotIn(token, self.client.get(reverse("profile")).content.decode())
        response = self.client.get(reverse("recovery-codes"))
        self.assertEqual(response.status_code, 302)

    def test_verify_second_factor_returns_to_safe_page(self) -> None:
        self.create_totp_device()
        url = reverse("verify-second-factor")
        response = self.client.get(url, {"next": reverse("profile")})
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}),
            response["Location"],
        )

        self.mark_recent_second_factor()
        self.assertRedirects(
            self.client.get(url, {"next": reverse("profile")}), reverse("profile")
        )
        self.assertRedirects(
            self.client.get(url, {"next": "//evil.example/"}), reverse("profile")
        )
        for destination in (
            reverse("data_project", kwargs={"project": self.project.slug}),
            reverse("manage-access", kwargs={"project": self.project.slug}),
        ):
            with self.subTest(destination=destination):
                self.assertRedirects(
                    self.client.get(url, {"next": destination}),
                    destination,
                    fetch_redirect_response=False,
                )
        for unsafe_url in (
            "https://evil.example/",
            "/\\evil.example/",
            "/accounts/profile/?next=//evil.example/",
        ):
            with self.subTest(unsafe_url=unsafe_url):
                self.assertRedirects(
                    self.client.get(url, {"next": unsafe_url}), reverse("profile")
                )

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
