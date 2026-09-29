# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for user middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.test import AsyncClient, TestCase, modify_settings, override_settings
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_string
from sentry_sdk.integrations.django.middleware import (
    _wrap_middleware,  # ruff: ignore[import-private-name]
)

from weblate.auth.models import User, get_anonymous
from weblate.legal.models import Agreement

if TYPE_CHECKING:
    from django.http import HttpRequest

    from weblate.auth.models import AuthenticatedHttpRequest


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

    def test_authenticated_session_expiry_is_not_refreshed_every_request(self) -> None:
        user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_login(user)

        response = self.client.get("/healthz/")
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)

        response = self.client.get("/healthz/")
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)


@modify_settings(MIDDLEWARE={"append": "weblate.legal.middleware.RequireTOSMiddleware"})
class ASGIMiddlewareTest(TestCase):
    """Exercise authentication and legal middleware through the async handler."""

    @staticmethod
    def import_sentry_middleware(path: str) -> type:
        # Exercise Sentry's async dispatch without installing global SDK patches.
        return _wrap_middleware(import_string(path), path)

    def test_anonymous_home(self) -> None:
        for sentry in (False, True):
            with (
                self.subTest(sentry=sentry),
                patch(
                    "django.core.handlers.base.import_string",
                    self.import_sentry_middleware if sentry else import_string,
                ),
            ):
                response = async_to_sync(AsyncClient().get)("/")
                self.assertEqual(response.status_code, 200)
                request = cast("AuthenticatedHttpRequest", response.asgi_request)
                self.assertEqual(request.user, get_anonymous())
                self.assertFalse(request.user.is_authenticated)
                self.assertIs(async_to_sync(request.auser)(), request.user)
                self.assertFalse(request.user.is_verified())

    def test_authenticated_home(self) -> None:
        user = User.objects.create_user(username="asgiuser", password="testpass")
        user.profile.language = "cs"
        user.profile.save()
        Agreement.objects.update_or_create(
            user=user, defaults={"tos": Agreement.current_tos_date()}
        )

        for sentry in (False, True):
            with (
                self.subTest(sentry=sentry),
                patch(
                    "django.core.handlers.base.import_string",
                    self.import_sentry_middleware if sentry else import_string,
                ),
            ):
                client = AsyncClient()
                client.force_login(user)
                response = async_to_sync(client.get)("/")
                self.assertEqual(response.status_code, 200)
                request = cast("AuthenticatedHttpRequest", response.asgi_request)
                self.assertEqual(request.user, user)
                self.assertIs(async_to_sync(request.auser)(), request.user)
                self.assertFalse(request.user.is_verified())
                self.assertEqual(request.LANGUAGE_CODE, "cs")
                self.assertEqual(
                    response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "cs"
                )

    def test_outdated_terms(self) -> None:
        user = User.objects.create_user(username="asgiuser", password="testpass")
        Agreement.objects.update_or_create(user=user, defaults={"tos": "1970-01-01"})

        for sentry in (False, True):
            with (
                self.subTest(sentry=sentry),
                patch(
                    "django.core.handlers.base.import_string",
                    self.import_sentry_middleware if sentry else import_string,
                ),
            ):
                client = AsyncClient()
                client.force_login(user)
                response = async_to_sync(client.get)("/")
                self.assertRedirects(
                    response,
                    f"{reverse('legal:confirm')}?next=%2F",
                    fetch_redirect_response=False,
                )
