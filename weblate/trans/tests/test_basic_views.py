# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for data exports."""

from unittest.mock import patch

from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.context_processors import weblate_context
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.about import AboutView
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

    def test_keys(self) -> None:
        ensure_ssh_key()
        response = self.client.get(reverse("keys"))
        self.assertContains(response, "SSH")

    def test_stats(self) -> None:
        response = self.client.get(reverse("stats"))
        self.assertContains(response, "Weblate statistics")

    def test_donate(self) -> None:
        response = self.client.get(reverse("donate"))
        self.assertContains(response, "Support Weblate")

    def test_healthz(self) -> None:
        response = self.client.get(reverse("healthz"))
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
