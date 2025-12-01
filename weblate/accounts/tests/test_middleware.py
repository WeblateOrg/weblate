# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for user middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_not_required
from django.test import TestCase, override_settings
from django.utils.decorators import method_decorator

from weblate.auth.models import User

if TYPE_CHECKING:
    from django.http import HttpRequest


class MiddlewareTest(TestCase):
    """
    Tests for Django's LoginRequiredMiddleware integration.

    Since Django 5.1, Weblate uses the built-in LoginRequiredMiddleware
    instead of the custom RequireLoginMiddleware. These tests verify that
    the middleware correctly enforces authentication when REQUIRE_LOGIN is enabled.
    """

    @method_decorator(login_not_required)
    def public_view(self, request: HttpRequest) -> str:
        """View not requiring login."""
        return "PUBLIC_VIEW"

    def protected_view(self, request: HttpRequest) -> str:
        """View requiring login."""
        return "PROTECTED_VIEW"

    @override_settings(
        REQUIRE_LOGIN=True,
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "weblate.accounts.middleware.AuthenticationMiddleware",
            "django.contrib.auth.middleware.LoginRequiredMiddleware",
        ],
    )
    def test_login_required_middleware(self) -> None:
        """Test that LoginRequiredMiddleware protects views when REQUIRE_LOGIN is True."""
        # Test public endpoint (health check)
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)

        # Test that anonymous users are redirected from protected views
        response = self.client.get("/projects/")
        self.assertRedirects(
            response, "/accounts/login/?next=/projects/", fetch_redirect_response=False
        )

        # Test that authenticated users can access protected views
        user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(user)
        response = self.client.get("/projects/")
        self.assertEqual(response.status_code, 200)

        # Test that admin login page is accessible without authentication
        self.client.logout()
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_no_login_required(self) -> None:
        """Test that views are accessible without authentication when REQUIRE_LOGIN is False."""
        # Test that anonymous users can access public endpoints
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)

        # With default settings (REQUIRE_LOGIN=False), most views are accessible
        response = self.client.get("/projects/")
        self.assertEqual(response.status_code, 200)
