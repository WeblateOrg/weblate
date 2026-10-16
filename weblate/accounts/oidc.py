# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import secrets
import time
from typing import TYPE_CHECKING, TypedDict, cast
from urllib.parse import urlsplit

from django.core.exceptions import BadRequest
from django.http import HttpResponseBadRequest, QueryDict
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext

if TYPE_CHECKING:
    from django.http import HttpRequest

OIDC_ATTEMPTS_SESSION_KEY = "weblate:oidc_attempts"
OIDC_ATTEMPT_PARAMETER = "_weblate_oidc_attempt"
OIDC_ATTEMPT_LIMIT = 16
OIDC_ATTEMPT_LIFETIME = 15 * 60


class OidcAttempt(TypedDict):
    target: str
    require_fresh: bool
    created: float
    login_completed: bool


class InvalidOidcAttempt(BadRequest):
    """The authorization attempt has expired or its parameters have changed."""


def oidc_login_error() -> HttpResponseBadRequest:
    return HttpResponseBadRequest(
        gettext(
            "This sign-in request has expired or changed. Start signing in again from the application."
        ),
        content_type="text/plain",
    )


def get_oidc_attempts(request: HttpRequest) -> dict[str, OidcAttempt]:
    stored = cast(
        "dict[str, OidcAttempt]", request.session.get(OIDC_ATTEMPTS_SESSION_KEY, {})
    )
    cutoff = time.time() - OIDC_ATTEMPT_LIFETIME
    attempts = {
        key: value for key, value in stored.items() if value["created"] > cutoff
    }
    if attempts != stored:
        request.session[OIDC_ATTEMPTS_SESSION_KEY] = attempts
    return attempts


def consent_parameters(params: QueryDict) -> dict[str, object]:
    """Compare the protocol fields carried by the toolkit's hidden form."""
    result: dict[str, object] = {
        key: params.get(key, "")
        for key in (
            "client_id",
            "redirect_uri",
            "response_type",
            "state",
            "nonce",
            "code_challenge",
            "code_challenge_method",
            "max_age",
        )
    }
    result["scope"] = params.get("scope", "").split()
    result["resource"] = [
        item for value in params.getlist("resource") for item in value.split()
    ]
    claims = params.get("claims", "")
    result["claims"] = json.loads(claims) if claims else None
    return result


def get_oidc_attempt(
    request: HttpRequest, target: str | None = None
) -> tuple[str, OidcAttempt] | None:
    consent = target is None and request.method == "POST"
    parts = urlsplit(target if target is not None else request.get_full_path())
    params = request.POST.copy() if consent else QueryDict(parts.query).copy()
    identifiers = params.pop(OIDC_ATTEMPT_PARAMETER, [])
    if not identifiers or (consent and identifiers == [""]):
        return None
    if len(identifiers) != 1 or parts.scheme or parts.netloc or parts.fragment:
        raise InvalidOidcAttempt
    identifier = identifiers[0]
    attempt = get_oidc_attempts(request).get(identifier)
    if attempt is None:
        raise InvalidOidcAttempt
    expected = urlsplit(attempt["target"])
    expected_params = QueryDict(expected.query)
    try:
        matches = (
            consent_parameters(params) == consent_parameters(expected_params)
            if consent
            else params == expected_params
        )
    except (ValueError, TypeError) as error:
        raise InvalidOidcAttempt from error
    if parts.path != expected.path or not matches:
        raise InvalidOidcAttempt
    return identifier, attempt


def create_oidc_attempt(
    request: HttpRequest, target: str, *, require_fresh: bool
) -> str:
    attempts = get_oidc_attempts(request).copy()
    if len(attempts) >= OIDC_ATTEMPT_LIMIT:
        del attempts[min(attempts, key=lambda key: attempts[key]["created"])]
    identifier = secrets.token_urlsafe(24)
    attempts[identifier] = {
        "target": target,
        "require_fresh": require_fresh,
        "created": time.time(),
        "login_completed": False,
    }
    request.session[OIDC_ATTEMPTS_SESSION_KEY] = attempts
    return identifier


def finish_oidc_attempt(request: HttpRequest) -> None:
    params = request.POST if request.method == "POST" else request.GET
    identifier = params.get(OIDC_ATTEMPT_PARAMETER)
    attempts = get_oidc_attempts(request).copy()
    if identifier is not None and identifier in attempts:
        del attempts[identifier]
        if attempts:
            request.session[OIDC_ATTEMPTS_SESSION_KEY] = attempts
        else:
            request.session.pop(OIDC_ATTEMPTS_SESSION_KEY, None)
            if not request.user.is_authenticated:
                request.session.pop("oidc_only", None)


def select_oidc_login(
    request: HttpRequest, target: str | None, *, authenticated: bool
) -> tuple[str, OidcAttempt] | None:
    selected = get_oidc_attempt(request, target) if target is not None else None
    if selected is not None:
        if not authenticated:
            request.session["oidc_only"] = True
        return selected
    if target is not None:
        try:
            authorization_url = reverse("oauth2_provider:authorize")
        except NoReverseMatch:
            pass
        else:
            # An authorization continuation must come from the provider, which
            # always supplies an attempt ID. Do not turn a stripped or stale
            # continuation into an ordinary, longer-lived login.
            if urlsplit(target).path == authorization_url:
                raise InvalidOidcAttempt
    get_oidc_attempts(request)
    if OIDC_ATTEMPTS_SESSION_KEY in request.session:
        saved_next = request.session.get("next")
        if saved_next and OIDC_ATTEMPT_PARAMETER in QueryDict(
            urlsplit(saved_next).query
        ):
            request.session.pop("next")
        request.session.pop(OIDC_ATTEMPTS_SESSION_KEY, None)
        if (
            not authenticated
            or request.session.get("weblate:session_expiry_scope") != "oidc"
        ):
            request.session.pop("oidc_only", None)
    return None


def prepare_oidc_login(
    request: HttpRequest, target: str | None
) -> HttpResponseBadRequest | None:
    try:
        select_oidc_login(request, target, authenticated=request.user.is_authenticated)
    except InvalidOidcAttempt:
        return oidc_login_error()
    return None
