# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import AnonymousUser
from django.utils.functional import SimpleLazyObject
from django.utils.translation import activate, get_language, get_language_from_request
from django_otp.middleware import OTPMiddleware

from weblate.accounts.models import set_lang_cookie
from weblate.accounts.utils import adjust_session_expiry
from weblate.auth.models import get_anonymous

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def get_user(request: AuthenticatedHttpRequest):
    """
    Based on django.contrib.auth.middleware.get_user.

    Adds handling of anonymous user which is stored in database.
    """
    if not hasattr(request, "weblate_cached_user"):
        user = auth.get_user(request)
        if isinstance(user, AnonymousUser):
            user = get_anonymous()
            # Make sure user permissions are fetched again, needed as
            # get_anonymous() is reusing same instance.
            user.clear_cache()

        request.weblate_cached_user = user
    return request.weblate_cached_user


class AuthenticationMiddleware(OTPMiddleware):
    """
    Copy of django.contrib.auth.middleware.AuthenticationMiddleware.

    It subclasses OTPMiddleware to get access to _verify_user_sync.
    """

    def __call__(self, request: AuthenticatedHttpRequest):
        from weblate.lang.models import Language

        # Django uses lazy object here, but we need the user in pretty
        # much every request, so there is no reason to delay this
        request.user = user = get_user(request)
        self._verify_user_sync(request, user)

        # Get language to use in this request
        if user.is_authenticated and user.profile.language:
            language = user.profile.language
        else:
            language = get_language_from_request(request)

        request.accepted_language = SimpleLazyObject(
            lambda: Language.objects.get_request_language(request)
        )

        # Extend session expiry for authenticated users
        if user.is_authenticated:
            adjust_session_expiry(request=request, user=user, is_login=False)

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
