# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for user middleware."""

from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from django.test.utils import override_settings

from weblate.accounts.middleware import RequireLoginMiddleware
from weblate.auth.models import User, get_anonymous


class MiddlewareTest(TestCase):
    def view_method(self) -> str:
        return "VIEW"

    def test_disabled(self) -> None:
        middleware = RequireLoginMiddleware()
        request = HttpRequest()
        self.assertIsNone(middleware.process_view(request, self.view_method, (), {}))

    @override_settings(LOGIN_REQUIRED_URLS=(r"/project/(.*)$",))
    def test_protect_project(self) -> None:
        middleware = RequireLoginMiddleware()
        request = HttpRequest()
        request.user = User()
        request.META["SERVER_NAME"] = "testserver"
        request.META["SERVER_PORT"] = "80"
        # No protection for not protected path
        self.assertIsNone(middleware.process_view(request, self.view_method, (), {}))
        request.path = "/project/foo/"
        # No protection for protected path and signed in user
        self.assertIsNone(middleware.process_view(request, self.view_method, (), {}))
        # Protection for protected path and not signed in user
        request.user = get_anonymous()
        self.assertIsInstance(
            middleware.process_view(request, self.view_method, (), {}),
            HttpResponseRedirect,
        )
        # No protection for login and not signed in user
        request.path = "/accounts/login/"
        self.assertIsNone(middleware.process_view(request, self.view_method, (), {}))
