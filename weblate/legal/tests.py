#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Test for legal stuff."""

from django.http import HttpRequest
from django.test import TestCase
from django.test.utils import modify_settings, override_settings
from django.urls import reverse

from weblate.accounts.tests.test_registration import REGISTRATION_DATA
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.utils import create_test_user


class LegalTest(TestCase, RegistrationTestMixin):
    def test_index(self):
        response = self.client.get(reverse("legal:index"))
        self.assertContains(response, "Legal Terms Overview")

    def test_terms(self):
        response = self.client.get(reverse("legal:terms"))
        self.assertContains(response, "Terms of Service")

    def test_cookies(self):
        response = self.client.get(reverse("legal:cookies"))
        self.assertContains(response, "Cookies Policy")

    def test_security(self):
        response = self.client.get(reverse("legal:security"))
        self.assertContains(response, "Security Policy")

    def test_contracts(self):
        response = self.client.get(reverse("legal:contracts"))
        self.assertContains(response, "Subcontractors")

    @modify_settings(
        SOCIAL_AUTH_PIPELINE={"append": "weblate.legal.pipeline.tos_confirm"}
    )
    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_confirm(self):
        """TOS confirmation on social auth."""
        response = self.client.post(reverse("register"), REGISTRATION_DATA, follow=True)
        # Check we did succeed
        self.assertContains(response, "Thank you for registering.")

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
    def test_middleware(self):
        user = create_test_user()
        # Unauthenticated
        response = self.client.get(reverse("home"), follow=True)
        self.assertContains(response, "Browse all 0 projects")
        # Login
        self.client.login(username="testuser", password="testpassword")
        # Chck that homepage redirects
        response = self.client.get(reverse("home"), follow=True)
        self.assertTrue(
            response.redirect_chain[-1][0].startswith(reverse("legal:confirm"))
        )
        # Check that contact works even without TOS
        response = self.client.get(reverse("contact"), follow=True)
        self.assertContains(response, "You can contact maintainers")
        # Confirm current TOS
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        user.agreement.make_current(request)
        # Homepage now should work
        response = self.client.get(reverse("home"), follow=True)
        self.assertContains(response, "Suggested translations")
