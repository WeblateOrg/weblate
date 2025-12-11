# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for legal stuff."""

from django.http import HttpRequest
from django.test import TestCase
from django.test.utils import modify_settings, override_settings
from django.urls import reverse

from weblate.accounts.tests.test_registration import (
    REGISTRATION_DATA,
    REGISTRATION_SUCCESS,
)
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.utils import create_test_user


class LegalTest(TestCase, RegistrationTestMixin):
    def test_index(self) -> None:
        response = self.client.get(reverse("legal:index"))
        self.assertContains(response, "Legal Terms Overview")

    def test_terms(self) -> None:
        response = self.client.get(reverse("legal:terms"))
        self.assertContains(response, "General Terms and Conditions")

    def test_cookies(self) -> None:
        response = self.client.get(reverse("legal:cookies"))
        self.assertContains(response, "Cookies Policy")

    def test_contracts(self) -> None:
        response = self.client.get(reverse("legal:contracts"))
        self.assertContains(response, "Subcontractors")

    @modify_settings(
        SOCIAL_AUTH_PIPELINE={"append": "weblate.legal.pipeline.tos_confirm"}
    )
    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_confirm(self) -> None:
        """TOS confirmation on social auth."""
        response = self.client.post(reverse("register"), REGISTRATION_DATA, follow=True)
        # Check we did succeed
        self.assertContains(response, REGISTRATION_SUCCESS)

        # Follow link
        url = self.assert_registration_mailbox()
        response = self.client.get(url, follow=True)
        self.assertTrue(
            response.redirect_chain[-1][0].startswith(reverse("legal:confirm"))
        )

        # Extract next URL
        url = response.context["form"].initial["next"]

        # Try invalid form (not checked)
        response = self.client.post(reverse("legal:confirm"), {"next": url})
        self.assertContains(response, "This field is required")

        # Actually confirm the TOS
        response = self.client.post(
            reverse("legal:confirm"), {"next": url, "confirm": 1}, follow=True
        )
        self.assertContains(response, "Your profile")

    @modify_settings(
        MIDDLEWARE={"append": "weblate.legal.middleware.RequireTOSMiddleware"}
    )
    def test_middleware(self) -> None:
        user = create_test_user()
        # Unauthenticated
        response = self.client.get(reverse("home"), follow=True)
        self.assertContains(response, "Browse all 0 projects")
        # Login
        self.client.login(username="testuser", password="testpassword")
        # Check that homepage redirects
        response = self.client.get(reverse("home"), follow=True)
        self.assertTrue(
            response.redirect_chain[-1][0].startswith(reverse("legal:confirm"))
        )
        # Check that contact works even without TOS
        response = self.client.get(reverse("contact"), follow=True)
        self.assertContains(response, "You can only contact administrators")
        # Confirm current TOS
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        user.agreement.make_current(request)
        # Homepage now should work
        response = self.client.get(reverse("home"), follow=True)
        self.assertContains(response, "Suggested translations")
