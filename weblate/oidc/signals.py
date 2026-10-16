# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import BACKEND_SESSION_KEY, REDIRECT_FIELD_NAME, load_backend
from django.utils import timezone
from oauth2_provider.models import AccessToken, Grant, IDToken, RefreshToken
from social_core.backends.base import BaseAuth
from social_core.backends.email import EmailAuth

from weblate.accounts.oidc import (
    OIDC_ATTEMPTS_SESSION_KEY,
    get_oidc_attempts,
    select_oidc_login,
)
from weblate.oidc.settings import AUTH_TIME_SESSION_KEY

if TYPE_CHECKING:
    from django.http import HttpRequest

    from weblate.auth.models import User


def record_authentication_time(
    sender: type[User], request: HttpRequest, user: User, **kwargs: object
) -> None:
    backend = load_backend(request.session[BACKEND_SESSION_KEY])
    strategy = getattr(request, "social_strategy", None)
    if isinstance(backend, BaseAuth) and strategy is not None:
        next_url = strategy.session_get(REDIRECT_FIELD_NAME)
    else:
        next_url = request.POST.get(
            REDIRECT_FIELD_NAME, request.GET.get(REDIRECT_FIELD_NAME)
        )
    selected = select_oidc_login(request, next_url, authenticated=user.is_authenticated)
    if selected is not None:
        identifier, attempt = selected
        attempts = get_oidc_attempts(request).copy()
        attempts[identifier] = {**attempt, "login_completed": True}
        request.session[OIDC_ATTEMPTS_SESSION_KEY] = attempts
    # Federation callbacks can silently reuse an upstream session. Its actual
    # authentication time is unknown, so never substitute the callback time.
    if isinstance(backend, BaseAuth) and not isinstance(backend, EmailAuth):
        request.session[AUTH_TIME_SESSION_KEY] = None
    else:
        request.session[AUTH_TIME_SESSION_KEY] = int(timezone.now().timestamp())


def revoke_user_credentials(
    sender: type[User], instance: User, **kwargs: object
) -> None:
    """Account removal anonymizes users, so explicitly delete their credentials."""
    RefreshToken.objects.filter(user=instance).delete()
    AccessToken.objects.filter(user=instance).delete()
    Grant.objects.filter(user=instance).delete()
    IDToken.objects.filter(user=instance).delete()
