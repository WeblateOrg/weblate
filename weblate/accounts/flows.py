# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired

from weblate.utils.email import email_key

if TYPE_CHECKING:
    from social_core.strategy import BaseStrategy

EMAIL_SENT_SESSION = "registration-email-sent"

# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_EMAIL_SESSION = "password_reset_email"
# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_USER_SESSION = "password_reset_user"
# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_SCOPE_SESSION = "password_reset_scope"
# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_SCOPE_TOKEN_PARAM = "password_reset_scope"
# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_SCOPE_TOKEN_SESSION = "password_reset_scope_token"
# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_SCOPE_SIGNING_SALT = "weblate.accounts.password-reset-scope"
# ruff: ignore[hardcoded-password-string]
PASSWORD_RESET_SCOPE_WEBLATE_SERVICES = "weblate-services"
PASSWORD_RESET_SCOPES = frozenset({PASSWORD_RESET_SCOPE_WEBLATE_SERVICES})


def get_email_link_lifetime(strategy: BaseStrategy[object], backend: str) -> int | None:
    """Return the shorter enabled lifetime for the code and its paused flow."""
    code_lifetime = settings.SOCIAL_AUTH_EMAIL_VALIDATION_EXPIRED_THRESHOLD
    partial_lifetime = (
        strategy.setting(
            "PARTIAL_PIPELINE_EXPIRED_THRESHOLD", 7 * 24 * 60 * 60, backend=backend
        )
        if strategy.EXPIRE_PARTIAL_PIPELINES_ON_LOAD
        else None
    )
    return min(filter(None, (code_lifetime, partial_lifetime)), default=None)


def sign_password_reset_scope(scope: str, email: str) -> str:
    """Sign password reset scope for the given e-mail address."""
    if scope not in PASSWORD_RESET_SCOPES:
        msg = "Unsupported password reset scope"
        raise ValueError(msg)
    return signing.dumps(
        {"scope": scope, "email": email_key(email.strip())},
        salt=PASSWORD_RESET_SCOPE_SIGNING_SALT,
    )


def get_signed_password_reset_scope(token: str, email: str | None = None) -> str:
    """Return trusted password reset scope from a signed token."""
    try:
        data = signing.loads(
            token,
            max_age=settings.SOCIAL_AUTH_EMAIL_VALIDATION_EXPIRED_THRESHOLD or None,
            salt=PASSWORD_RESET_SCOPE_SIGNING_SALT,
        )
    except (BadSignature, SignatureExpired):
        return ""

    if not isinstance(data, dict):
        return ""

    scope = data.get("scope")
    token_email = data.get("email")
    if scope not in PASSWORD_RESET_SCOPES or not isinstance(token_email, str):
        return ""
    if email is not None and token_email != email_key(email.strip()):
        return ""
    return scope
