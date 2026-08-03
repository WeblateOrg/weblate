# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

from json import JSONDecodeError
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.templatetags.static import static
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.context_processors import weblate_context
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.about import FALLBACK_STATS, AboutView, DonateView
from weblate.trans.views.error import server_error
from weblate.utils.version import GIT_VERSION, VERSION
from weblate.utils.version_display import (
    VERSION_DISPLAY_HIDE,
    VERSION_DISPLAY_SHOW,
    VERSION_DISPLAY_SOFT,
)
from weblate.vcs.ssh import ensure_ssh_key


class BasicViewTest(FixtureTestCase):
    def test_about(self) -> None:
        response = self.client.get(reverse("about"))
        self.assertContains(response, "translate-toolkit")

    @override_settings(GOOGLE_ANALYTICS_ID="UA-123")
    def test_google_analytics(self) -> None:
        response = self.client.get(reverse("about"))
        self.assertContains(response, static("js/google-analytics.js"))
        self.assertContains(response, 'data-tracking-id="UA-123"')
        self.assertNotContains(response, "GoogleAnalyticsObject")
        script_src = next(
            directive
            for directive in response["Content-Security-Policy"].split(";")
            if directive.strip().startswith("script-src ")
        )
        self.assertIn("www.google-analytics.com", script_src)
        self.assertNotIn("'unsafe-inline'", script_src)

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    @patch("weblate.trans.views.error.last_event_id", return_value="event-id")
    def test_sentry_feedback(self, _last_event_id) -> None:
        request = self.client.get(
            reverse("about"), headers={"accept": "text/html"}
        ).wsgi_request

        response = server_error(request)

        self.assertContains(response, static("js/vendor/sentry.js"), status_code=500)
        self.assertContains(response, static("js/sentry-feedback.js"), status_code=500)
        self.assertContains(
            response,
            'data-dsn="https://public@example.com/1"',
            status_code=500,
        )
        self.assertContains(response, 'data-event-id="event-id"', status_code=500)
        self.assertContains(response, 'data-user-name="Weblate Test"', status_code=500)
        self.assertContains(
            response,
            'data-user-email="weblate@example.org"',
            status_code=500,
        )
        self.assertNotContains(response, "Sentry.init", status_code=500)

    @override_settings(
        MATOMO_SITE_ID="123",
        MATOMO_URL="https://matomo.example.com/",
    )
    def test_matomo(self) -> None:
        response = self.client.get(self.project_url)
        self.assertContains(response, static("js/matomo.js"))
        self.assertContains(response, 'data-url="https://matomo.example.com/"')
        self.assertContains(response, 'data-site-id="123"')
        self.assertContains(response, 'data-language="en"')
        self.assertContains(response, f'data-project="{self.project.name}"')
        self.assertNotContains(response, "setTrackerUrl")
        script_src = next(
            directive
            for directive in response["Content-Security-Policy"].split(";")
            if directive.strip().startswith("script-src ")
        )
        self.assertIn("matomo.example.com", script_src)
        self.assertNotIn("'unsafe-inline'", script_src)

    def test_keys(self) -> None:
        ensure_ssh_key()
        response = self.client.get(reverse("keys"))
        self.assertContains(response, "SSH")

    def test_stats(self) -> None:
        response = self.client.get(reverse("stats"))
        self.assertContains(response, "Weblate statistics")

    def test_stats_without_active_users(self) -> None:
        self.client.logout()
        User.objects.update(is_active=False)

        response = self.client.get(reverse("stats"))

        self.assertContains(response, "Weblate statistics")

    def test_donate(self) -> None:
        response = self.client.get(reverse("donate"))
        self.assertContains(response, "Support Weblate")

    def test_donate_falls_back_on_malformed_github_json(self) -> None:
        errors = (
            JSONDecodeError("Invalid JSON", "", 0),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        )

        for error in errors:
            with self.subTest(error=error):
                cache.delete(DonateView.cache_key)
                with patch.object(DonateView, "fetch_url", side_effect=error):
                    self.assertEqual(DonateView().get_stats(), FALLBACK_STATS)

    def test_healthz(self) -> None:
        response = self.client.get(reverse("healthz"))
        self.assertContains(response, "ok")

    def test_healthz_asgi(self) -> None:
        response = async_to_sync(self.async_client.get)(reverse("healthz"))
        self.assertContains(response, "ok")

    @patch(
        "weblate.trans.context_processors.get_support_status",
        return_value={
            "name": "",
            "is_hosted_weblate": False,
            "is_dedicated": False,
            "has_support": False,
            "has_expired_support": False,
            "in_limits": True,
            "backup_repository": "",
        },
    )
    def test_context_processor_without_user(self, _mocked_support_status) -> None:
        request = RequestFactory().get("/")
        context = weblate_context(request)
        self.assertIn("show_version_details", context)
        self.assertEqual(context["theme"], "auto")

    def get_context_description(self) -> str:
        request = RequestFactory().get("/")
        with patch(
            "weblate.trans.context_processors.get_support_status", return_value={}
        ):
            return weblate_context(request)["description"]

    @override_settings(OFFER_HOSTING=True, SINGLE_PROJECT=False)
    def test_context_processor_hosted_description(self) -> None:
        self.assertEqual(
            self.get_context_description(),
            "Hosted Weblate, the place to localize your software project.",
        )

    @override_settings(OFFER_HOSTING=False, SINGLE_PROJECT=False)
    def test_context_processor_multi_project_description(self) -> None:
        self.assertEqual(
            self.get_context_description(),
            "This site runs Weblate for localizing various software projects.",
        )

    @override_settings(OFFER_HOSTING=False, SINGLE_PROJECT=True)
    def test_context_processor_single_project_description(self) -> None:
        self.assertEqual(
            self.get_context_description(),
            "This site runs Weblate for localizing a software project.",
        )

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_SHOW, HIDE_VERSION=False)
    def test_about_footer_shows_version_in_show_mode(self) -> None:
        response = self.client.get(reverse("about"))
        self.assertContains(
            response,
            f'Powered by <a href="https://weblate.org/">Weblate {VERSION}</a>',
            html=True,
        )
        self.assertContains(response, f"<span>{GIT_VERSION}</span>", html=True)

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_SOFT, HIDE_VERSION=False)
    def test_about_footer_hides_version_in_soft_mode(self) -> None:
        response = self.client.get(reverse("about"))
        self.assertContains(
            response,
            'Powered by <a href="https://weblate.org/">Weblate</a>',
            html=True,
        )
        self.assertContains(response, f"<span>{GIT_VERSION}</span>", html=True)

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_HIDE, HIDE_VERSION=True)
    def test_about_hides_details_for_regular_users_only(self) -> None:
        response = self.client.get(reverse("about"))
        self.assertContains(
            response,
            'Powered by <a href="https://weblate.org/">Weblate</a>',
            html=True,
        )
        self.assertNotContains(response, f"<span>{GIT_VERSION}</span>", html=False)

        admin = User.objects.create_superuser(
            "admin", "admin@example.com", "testpassword"
        )
        request = self.get_request(user=admin)
        request.path = reverse("about")
        response = AboutView.as_view()(request)
        response.render()
        self.assertContains(response, f"<span>{GIT_VERSION}</span>", html=True)
