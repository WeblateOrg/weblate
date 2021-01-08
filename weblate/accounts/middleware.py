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

import re

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.utils.translation import activate, get_language, get_language_from_request

from weblate.accounts.models import set_lang_cookie
from weblate.accounts.utils import adjust_session_expiry
from weblate.auth.models import get_anonymous


def get_user(request):
    """Based on django.contrib.auth.middleware.get_user.

    Adds handling of anonymous user which is stored in database.
    """
    # pylint: disable=protected-access
    if not hasattr(request, "_cached_user"):
        user = auth.get_user(request)
        if isinstance(user, AnonymousUser):
            user = get_anonymous()

        request._cached_user = user
    return request._cached_user


class AuthenticationMiddleware:
    """Copy of django.contrib.auth.middleware.AuthenticationMiddleware."""

    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        # Django uses lazy object here, but we need the user in pretty
        # much every request, so there is no reason to delay this
        request.user = user = get_user(request)

        # Get language to use in this request
        if user.is_authenticated and user.profile.language:
            language = user.profile.language
        else:
            language = get_language_from_request(request)

        # Extend session expiry for authenticated users
        if user.is_authenticated:
            adjust_session_expiry(request)

        # Based on django.middleware.locale.LocaleMiddleware
        activate(language)
        request.LANGUAGE_CODE = get_language()

        # Invoke the request
        response = self.get_response(request)

        # Update the language cookie if needed
        if user.is_authenticated and user.profile.language != request.COOKIES.get(
            settings.LANGUAGE_COOKIE_NAME
        ):
            set_lang_cookie(response, user.profile)

        return response


class RequireLoginMiddleware:
    """Middleware that applies the login_required decorator to matching URL patterns.

    To use, add the class to MIDDLEWARE and
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

    def __init__(self, get_response=None):
        self.get_response = get_response
        self.required = self.get_setting_re(settings.LOGIN_REQUIRED_URLS)
        self.exceptions = self.get_setting_re(settings.LOGIN_REQUIRED_URLS_EXCEPTIONS)

    def get_setting_re(self, setting):
        """Grab regexp list from settings and compiles them."""
        return tuple(
            re.compile(url.replace("{URL_PREFIX}", settings.URL_PREFIX))
            for url in setting
        )

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Check request whether it needs to enforce login for this URL."""
        # No need to process URLs if not configured
        if not self.required:
            return None

        # No need to process URLs if user already signed in
        if request.user.is_authenticated:
            return None

        # Let gitexporter handle authentication
        # - it doesn't go through standard Django authentication
        # - once HTTP_AUTHORIZATION is set, it enforces it
        if "weblate.gitexport" in settings.INSTALLED_APPS:
            # pylint: disable=wrong-import-position
            import weblate.gitexport.views

            if request.path.startswith("/git/"):
                if request.META.get("HTTP_AUTHORIZATION"):
                    return None
                return weblate.gitexport.views.response_authenticate()

        # An exception match should immediately return None
        for url in self.exceptions:
            if url.match(request.path):
                return None

        # Requests matching a restricted URL pattern are returned
        # wrapped with the login_required decorator
        for url in self.required:
            if url.match(request.path):
                return login_required(view_func)(request, *view_args, **view_kwargs)

        # Explicitly return None for all non-matching requests
        return None

    def __call__(self, request):
        return self.get_response(request)
