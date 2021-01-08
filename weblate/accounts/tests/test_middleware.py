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

"""Tests for user middleware."""

from django.http import HttpRequest, HttpResponseRedirect
from django.test import TestCase
from django.test.utils import override_settings

from weblate.accounts.middleware import RequireLoginMiddleware
from weblate.auth.models import User, get_anonymous


class MiddlewareTest(TestCase):
    def view_method(self):
        return "VIEW"

    def test_disabled(self):
        middleware = RequireLoginMiddleware()
        request = HttpRequest()
        self.assertIsNone(middleware.process_view(request, self.view_method, (), {}))

    @override_settings(LOGIN_REQUIRED_URLS=(r"/project/(.*)$",))
    def test_protect_project(self):
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
