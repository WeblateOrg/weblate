# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for account removal."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from django.core import mail
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from weblate.accounts.utils import (
    SECOND_FACTOR_VERIFY_SECONDS,
    SESSION_SECOND_FACTOR_TIMESTAMP,
)
from weblate.auth.models import User
from weblate.trans.tests.test_views import RegistrationTestMixin, ViewTestCase

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse


class AccountRemovalTest(ViewTestCase, RegistrationTestMixin):
    def test_page(self) -> None:
        response = self.client.get(reverse("remove"))
        self.assertContains(response, "Account removal deletes all your private data.")

    def verify_removal(self, response: _MonkeyPatchedWSGIResponse) -> None:
        self.assertRedirects(response, reverse("email-sent"))

        # Get confirmation URL
        url = self.assert_registration_mailbox("[Weblate] Account removal on Weblate")
        # Verify confirmation URL
        response = self.confirm_registration_url(url, follow=True)
        self.assertContains(
            response,
            "By pressing the following button, you will no longer be able to use",
        )
        # Confirm removal
        response = self.client.post(reverse("remove"), follow=True)
        self.assertContains(response, "Your account has been removed.")
        self.assertFalse(User.objects.filter(username="testuser").exists())

    def test_removal(self) -> None:
        response = self.client.post(
            reverse("remove"), {"password": "testpassword"}, follow=True
        )
        self.verify_removal(response)

    def test_removal_failed(self) -> None:
        response = self.client.post(
            reverse("remove"), {"password": "invalidpassword"}, follow=True
        )
        self.assertContains(response, "You have entered an invalid password.")
        self.assertTrue(User.objects.filter(username="testuser").exists())

    def test_removal_nopass(self) -> None:
        # Set unusable password for test user.
        self.user.set_unusable_password()
        self.user.save()
        # Need to force login as user has no password now.
        # In the app he would login by third party auth.
        self.client.force_login(self.user)
        response = self.client.post(reverse("remove"), {"password": ""}, follow=True)
        self.verify_removal(response)

    def test_removal_without_password_requires_recent_second_factor(self) -> None:
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        self.client.force_login(self.user)
        TOTPDevice.objects.create(user=self.user, confirmed=True)
        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()) - SECOND_FACTOR_VERIFY_SECONDS - 1,
        }
        session.save()
        url = reverse("remove")

        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}), response["Location"]
        )

        response = self.client.post(url, {"password": ""})
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}), response["Location"]
        )
        self.assertFalse(self.client.session.get("account_remove"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk, is_active=True).exists())

        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()),
        }
        session.save()
        response = self.client.post(url, {"password": ""}, follow=True)
        self.assertRedirects(response, reverse("email-sent"))
        confirmation_url = self.assert_registration_mailbox(
            "[Weblate] Account removal on Weblate"
        )
        response = self.confirm_registration_url(confirmation_url, follow=True)
        self.assertContains(response, "By pressing the following button")

        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()) - SECOND_FACTOR_VERIFY_SECONDS - 1,
        }
        session.save()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}), response["Location"]
        )
        self.assertTrue(User.objects.filter(pk=self.user.pk, is_active=True).exists())

        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()),
        }
        session.save()
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Your account has been removed.")
        self.assertFalse(User.objects.filter(pk=self.user.pk, is_active=True).exists())

    def test_removal_change(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        # We should have some change to commit
        self.assertTrue(self.component.needs_commit())
        # Remove account
        self.test_removal()
        # Changes should be committed
        self.assertFalse(self.component.needs_commit())
