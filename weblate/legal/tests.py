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
from weblate.api.spectacular import get_spectacular_settings
from weblate.legal.utils import get_hidden_documents
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.utils import create_test_user


class LegalTest(TestCase, RegistrationTestMixin):
    @override_settings(LEGAL_HIDDEN_DOCUMENTS=("", "contracts", " privacy "))
    def test_hidden_documents_normalized(self) -> None:
        self.assertEqual(get_hidden_documents(), {"contracts", "privacy"})

    def test_index(self) -> None:
        response = self.client.get(reverse("legal:index"))
        self.assertContains(response, "Legal Terms Overview")

    def test_terms(self) -> None:
        response = self.client.get(reverse("legal:terms"))
        self.assertContains(response, "General Terms and Conditions")
        self.assertContains(response, 'class="card-body tos"')

    @override_settings(LEGAL_DOCUMENT_CSS_CLASS="")
    def test_terms_without_document_css_class(self) -> None:
        response = self.client.get(reverse("legal:terms"))
        self.assertContains(response, 'class="card-body"')
        self.assertNotContains(response, 'class="card-body tos"')

    def test_cookies(self) -> None:
        response = self.client.get(reverse("legal:cookies"))
        self.assertContains(response, "Cookies Policy")

    @override_settings(
        LEGAL_HIDDEN_DOCUMENTS=("terms", "privacy"),
        LEGAL_URL="https://example.com/terms/",
        PRIVACY_URL="https://example.com/privacy/",
    )
    def test_cookies_hidden_document_links(self) -> None:
        response = self.client.get(reverse("legal:cookies"))
        self.assertContains(response, "https://example.com/terms/")
        self.assertContains(response, "https://example.com/privacy/")
        self.assertNotContains(response, reverse("legal:terms"))
        self.assertNotContains(response, reverse("legal:privacy"))

    def test_contracts(self) -> None:
        response = self.client.get(reverse("legal:contracts"))
        self.assertContains(response, "Subcontractors")

    @override_settings(LEGAL_HIDDEN_DOCUMENTS=("contracts",))
    def test_hidden_contracts(self) -> None:
        response = self.client.get(reverse("legal:terms"))
        self.assertContains(response, "General Terms and Conditions")
        self.assertNotContains(response, reverse("legal:contracts"))

        response = self.client.get(reverse("legal:contracts"))
        self.assertEqual(response.status_code, 404)

    @override_settings(LEGAL_DOCUMENT_CSS_CLASS="")
    def test_confirm_without_document_css_class(self) -> None:
        create_test_user()
        self.client.login(username="testuser", password="testpassword")

        response = self.client.get(reverse("legal:confirm"))
        self.assertContains(response, 'class="list-group-item pre-scrollable"')
        self.assertNotContains(response, 'class="list-group-item pre-scrollable tos"')

    @override_settings(
        LEGAL_HIDDEN_DOCUMENTS=("terms", "privacy"),
        LEGAL_URL="https://example.com/terms/",
        PRIVACY_URL="https://example.com/privacy/",
    )
    def test_confirm_external_documents(self) -> None:
        create_test_user()
        self.client.login(username="testuser", password="testpassword")

        response = self.client.get(reverse("legal:confirm"))
        self.assertContains(response, "https://example.com/terms/")
        self.assertContains(response, "https://example.com/privacy/")
        self.assertNotContains(response, reverse("legal:terms"))
        self.assertNotContains(response, reverse("legal:privacy"))
        self.assertNotContains(response, "no defined privacy terms of service")

    @override_settings(LEGAL_HIDDEN_DOCUMENTS=("terms",), LEGAL_URL=None)
    def test_confirm_without_external_terms(self) -> None:
        create_test_user()
        self.client.login(username="testuser", password="testpassword")

        response = self.client.get(reverse("legal:confirm"))
        self.assertContains(response, "no defined privacy terms of service")
        self.assertContains(
            response,
            "Please read the following General Terms and Conditions document",
        )
        self.assertNotContains(response, "Please read the following legal documents")

    def test_spectacular_tos_url(self) -> None:
        apps = ["weblate.legal"]
        settings = get_spectacular_settings(apps, "https://example.com", "Weblate")
        self.assertEqual(settings["TOS"], "/legal/terms/")

        settings = get_spectacular_settings(
            apps,
            "https://example.com",
            "Weblate",
            legal_hidden_documents=("terms",),
            legal_url="https://example.com/terms/",
        )
        self.assertEqual(settings["TOS"], "https://example.com/terms/")

        settings = get_spectacular_settings(
            apps,
            "https://example.com",
            "Weblate",
            legal_hidden_documents=("terms",),
        )
        self.assertNotIn("TOS", settings)

    def test_spectacular_logo_uses_stable_url(self) -> None:
        spectacular_settings = get_spectacular_settings(
            [],
            "https://example.com",
            "Weblate",
            static_url="https://cdn.example.com/static/",
        )
        logo_url = spectacular_settings["EXTENSIONS_INFO"]["x-logo"]["url"]
        self.assertIs(type(logo_url), str)
        self.assertEqual(logo_url, "https://cdn.example.com/static/weblate.svg")

    @modify_settings(
        SOCIAL_AUTH_PIPELINE={"append": "weblate.legal.pipeline.tos_confirm"}
    )
    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_confirm(self) -> None:
        """TOS confirmation on social auth."""
        registration_response = self.client.post(
            reverse("register"), REGISTRATION_DATA, follow=True
        )
        # Check we did succeed
        self.assertContains(registration_response, REGISTRATION_SUCCESS)

        # Follow link
        url = self.assert_registration_mailbox()
        response = self.confirm_registration_url(url, follow=True)
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
        self.assertContains(response, "How can we help?")
        # Confirm current TOS
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        user.agreement.make_current(request)
        # Homepage now should work
        response = self.client.get(reverse("home"), follow=True)
        self.assertContains(response, "Suggested translations")
