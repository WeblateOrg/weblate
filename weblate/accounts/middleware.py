# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import re

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.utils.functional import SimpleLazyObject

from weblate.accounts.models import get_anonymous


def get_user(request):
    """Based on django.contrib.auth.middleware.get_user

    Adds handling of anonymous user which is stored in database.
    """
    # pylint: disable=W0212
    if not hasattr(request, '_cached_user'):
        user = auth.get_user(request)
        if isinstance(user, AnonymousUser):
            user = get_anonymous()

        request._cached_user = user
    return request._cached_user


class AuthenticationMiddleware(object):
    """Copy of django.contrib.auth.middleware.AuthenticationMiddleware"""
    def process_request(self, request):
        request.user = SimpleLazyObject(lambda: get_user(request))


class RequireLoginMiddleware(object):
    """
    Middleware component that wraps the login_required decorator around
    matching URL patterns. To use, add the class to MIDDLEWARE_CLASSES and
    define LOGIN_REQUIRED_URLS and LOGIN_REQUIRED_URLS_EXCEPTIONS in your
    settings.py. For example:
    ------
    LOGIN_REQUIRED_URLS = (
        r'/topsecret/(.*)$',
    )
    LOGIN_REQUIRED_URLS_EXCEPTIONS = (
        r'/topsecret/login(.*)$',
        r'/topsecret/logout(.*)$',
    )
    ------
    LOGIN_REQUIRED_URLS is where you define URL patterns; each pattern must
    be a valid regex.

    LOGIN_REQUIRED_URLS_EXCEPTIONS is, conversely, where you explicitly
    define any exceptions (like login and logout URLs).
    """
    def __init__(self):
        self.required = self.get_setting_re(
            'LOGIN_REQUIRED_URLS',
            []
        )
        self.exceptions = self.get_setting_re(
            'LOGIN_REQUIRED_URLS_EXCEPTIONS',
            [r'/accounts/(.*)$', r'/static/(.*)$', r'/api/(.*)$']
        )

    def get_setting_re(self, name, default):
        """Grab regexp list from settings and compiles them"""
        return tuple(
            [re.compile(url) for url in getattr(settings, name, default)]
        )

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Check request whether it needs to enforce login for this URL based
        on defined parameters.
        """
        # No need to process URLs if not configured
        if len(self.required) == 0:
            return None

        # No need to process URLs if user already logged in
        if request.user.is_authenticated:
            return None

        # An exception match should immediately return None
        for url in self.exceptions:
            if url.match(request.path):
                return None

        # Requests matching a restricted URL pattern are returned
        # wrapped with the login_required decorator
        for url in self.required:
            if url.match(request.path):
                return login_required(view_func)(
                    request,
                    *view_args,
                    **view_kwargs
                )

        # Explicitly return None for all non-matching requests
        return None
