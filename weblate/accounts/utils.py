# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Literal

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.helpers import WebAuthnHelper
from django_otp_webauthn.models import WebAuthnCredential
from rest_framework.authtoken.models import Token
from social_django.models import Code

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.auth.models import User
from weblate.trans.signals import user_pre_delete
from weblate.utils.token import get_token

if TYPE_CHECKING:
    from django_otp.models import Device

    from weblate.accounts.types import DeviceType
    from weblate.auth.models import AuthenticatedHttpRequest

SESSION_WEBAUTHN_AUDIT = "weblate:second_factor:webauthn_audit_log"
SESSION_SECOND_FACTOR_USER = "weblate:second_factor:user"
SESSION_SECOND_FACTOR_TIMESTAMP = "weblate:second_factor:timestamp"
SESSION_SECOND_FACTOR_SOCIAL = "weblate:second_factor:social"
SESSION_SECOND_FACTOR_TOTP = "weblate:second_factor:totp_key"
SESSION_EXPIRY_SCOPE = "weblate:session_expiry_scope"
SESSION_EXPIRY_AGE = "weblate:session_expiry_age"
SESSION_EXPIRY_REFRESHED = "weblate:session_expiry_refreshed"
SESSION_EXPIRY_SCOPE_SAML = "saml"
SESSION_EXPIRY_SCOPE_2FA = "2fa"
SESSION_EXPIRY_SCOPE_LOGIN = "login"
SESSION_EXPIRY_SCOPE_AUTHENTICATED = "authenticated"
SESSION_EXPIRY_REFRESH_MIN_SECONDS = 60
SESSION_EXPIRY_REFRESH_MAX_SECONDS = 86_400
SESSION_EXPIRY_SAML_SECONDS = 60

SECOND_FACTOR_VERIFY_SECONDS = 600
SessionExpiryScope = Literal["saml", "2fa", "login", "authenticated"]


def create_api_token(user: User) -> Token:
    """Create an API token for a user."""
    return Token.objects.create(
        user=user, key=get_token("wlp" if user.is_bot else "wlu")
    )


def delete_api_tokens(user: User) -> None:
    """Delete all API tokens for a user."""
    Token.objects.filter(user=user).delete()


def reset_api_token(user: User) -> Token:
    """Reset API token for a user."""
    delete_api_tokens(user)
    return create_api_token(user)


def remove_user(
    user: User,
    request: AuthenticatedHttpRequest | None,
    *,
    activity: str = "removed",
    **params,
) -> None:
    """Remove user account."""
    # Send signal (to commit any pending changes)
    user_pre_delete.send(instance=user, sender=user.__class__)

    # Store activity log and notify
    AuditLog.objects.create(user, request, activity, **params)

    # Remove any email validation codes
    invalidate_reset_codes(user)

    # Change username
    user.username = f"deleted-{user.pk}"
    user.email = f"noreply+{user.pk}@weblate.org"
    while User.objects.filter(username=user.username).exists():
        user.username = f"deleted-{user.pk}-{os.urandom(5).hex()}"
    while User.objects.filter(email=user.email).exists():
        user.email = f"noreply+{user.pk}-{os.urandom(5).hex()}@weblate.org"

    # Remove user information
    user.full_name = "Deleted User"

    # Disable the user
    user.is_active = False
    user.set_unusable_password()
    user.save()

    # Remove all social auth associations
    user.social_auth.all().delete()

    # Remove user from all groups
    user.groups.clear()
    user.administered_group_set.clear()

    # Remove user translation memory
    user.memory_set.all().delete()

    # Clear subscriptions
    user.subscription_set.all().delete()
    user.profile.watched.clear()

    # Cleanup profile
    try:
        profile = user.profile
    except ObjectDoesNotExist:
        pass
    else:
        profile.website = ""
        profile.liberapay = ""
        profile.fediverse = ""
        profile.codesite = ""
        profile.github = ""
        profile.twitter = ""
        profile.linkedin = ""
        profile.location = ""
        profile.company = ""
        profile.public_email = ""
        profile.save()

    # Delete API tokens
    delete_api_tokens(user)


def lock_user(
    user: User,
    reason: Literal["locked", "admin-locked"],
    request: AuthenticatedHttpRequest | None = None,
) -> None:
    user.set_unusable_password()
    user.save(update_fields=["password"])
    AuditLog.objects.create(user, request, reason)


def get_all_user_mails(user: User, entries=None, filter_deliverable=True):
    """Return all verified mails for user."""
    kwargs = {"social__user": user}
    if entries:
        kwargs["social__in"] = entries
    if filter_deliverable:
        # filter out emails that are not deliverable
        emails = set(
            VerifiedEmail.objects.filter(is_deliverable=True, **kwargs).values_list(
                "email", flat=True
            )
        )
    else:
        # allow all emails, including non deliverable ones
        emails = set(
            VerifiedEmail.objects.filter(**kwargs).values_list("email", flat=True)
        )
    emails.add(user.email)
    emails.discard(None)  # type: ignore[arg-type]
    emails.discard("")
    return emails


def invalidate_reset_codes(user=None, entries=None, emails=None) -> None:
    """Invalidate email activation codes for a user."""
    if emails is None:
        emails = get_all_user_mails(user, entries)
    Code.objects.filter(email__in=emails).delete()


def cycle_session_keys(request: AuthenticatedHttpRequest, user: User) -> None:
    """
    Cycle session keys.

    Updating the password logs out all other sessions for the user
    except the current one and change key for current session.
    """
    # Change unusable password hash to be able to invalidate other sessions
    if not user.has_usable_password():
        user.set_unusable_password()
        user.save(update_fields=["password"])
    # Cycle session key
    update_session_auth_hash(request, user)


def get_session_expiry_refresh_seconds(expiry_age: int) -> int:
    """Return how often authenticated session expiry should be refreshed."""
    if expiry_age <= 1:
        return 0
    if expiry_age <= SESSION_EXPIRY_REFRESH_MIN_SECONDS:
        return max(expiry_age // 2, 1)
    return min(
        expiry_age - SESSION_EXPIRY_REFRESH_MIN_SECONDS,
        expiry_age // 2,
        SESSION_EXPIRY_REFRESH_MAX_SECONDS,
    )


def get_session_expiry_scope(
    *,
    request: AuthenticatedHttpRequest,
    user: User,
    is_login: bool,
) -> SessionExpiryScope:
    """Return the session expiry scope for current authentication state."""
    saml_only = bool(request.session.get("saml_only", False))
    if is_login:
        next_url = request.POST.get("next", request.GET.get("next"))
        if next_url == "/idp/login/process/":
            saml_only = True
            if request.session.get("saml_only") is not True:
                request.session["saml_only"] = True

    if saml_only:
        return SESSION_EXPIRY_SCOPE_SAML

    if (
        user.profile.has_2fa
        and DEVICE_ID_SESSION_KEY not in request.session
        and not user.is_verified()
    ):
        return SESSION_EXPIRY_SCOPE_2FA

    if is_login:
        return SESSION_EXPIRY_SCOPE_LOGIN

    return SESSION_EXPIRY_SCOPE_AUTHENTICATED


def get_session_expiry_age(scope: SessionExpiryScope) -> int:
    """Return session expiry age for a session scope."""
    if scope == SESSION_EXPIRY_SCOPE_SAML:
        return SESSION_EXPIRY_SAML_SECONDS
    if scope == SESSION_EXPIRY_SCOPE_2FA:
        return settings.SESSION_COOKIE_AGE_2FA
    if scope == SESSION_EXPIRY_SCOPE_LOGIN:
        return settings.SESSION_COOKIE_AGE
    return settings.SESSION_COOKIE_AGE_AUTHENTICATED


def should_update_session_expiry(
    *,
    request: AuthenticatedHttpRequest,
    scope: SessionExpiryScope,
    expiry_age: int,
    now: int,
    force: bool,
) -> bool:
    """Return whether session expiry metadata should be updated."""
    if force:
        return True
    if request.session.get(SESSION_EXPIRY_SCOPE) != scope:
        return True
    if request.session.get(SESSION_EXPIRY_AGE) != expiry_age:
        return True
    if scope != SESSION_EXPIRY_SCOPE_AUTHENTICATED:
        return False

    refreshed = request.session.get(SESSION_EXPIRY_REFRESHED)
    if not isinstance(refreshed, (int, float)):
        return True
    return now - refreshed >= get_session_expiry_refresh_seconds(expiry_age)


def adjust_session_expiry(
    *,
    request: AuthenticatedHttpRequest,
    user: User,
    is_login: bool = True,
    scope: SessionExpiryScope | None = None,
    force: bool = False,
) -> None:
    """
    Adjust session expiry based on scope.

    - Set longer expiry for authenticated users.
    - Set short lived session for SAML authentication flow.
    """
    if scope is None:
        scope = get_session_expiry_scope(
            request=request,
            user=user,
            is_login=is_login,
        )
    expiry_age = get_session_expiry_age(scope)
    now = int(time.time())
    if not should_update_session_expiry(
        request=request,
        scope=scope,
        expiry_age=expiry_age,
        now=now,
        force=force or is_login,
    ):
        return

    request.session.set_expiry(expiry_age)
    request.session[SESSION_EXPIRY_SCOPE] = scope
    request.session[SESSION_EXPIRY_AGE] = expiry_age
    request.session[SESSION_EXPIRY_REFRESHED] = now


def get_key_name(device: Device) -> str:
    # Prefer user provided name
    if device.name:
        return device.name

    device_id: str | int = device.id
    device_label = f"{device.__class__.__name__} (%s)"

    if isinstance(device, WebAuthnCredential):
        device_label = gettext("Security key (%s)")
        # GUID is often masked by browser and zeroed one is useless
        if device.aaguid != "00000000-0000-0000-0000-000000000000":
            device_id = device.aaguid

    elif isinstance(device, TOTPDevice):
        device_label = gettext("Authentication app (%s)")

    return device_label % device_id


def get_key_type(device: Device) -> DeviceType:
    if isinstance(device, WebAuthnCredential):
        return "webauthn"
    if isinstance(device, TOTPDevice):
        return "totp"
    if isinstance(device, StaticDevice):
        return "recovery"
    msg = f"Unsupported device: {device}"
    raise TypeError(msg)


class WeblateWebAuthnHelper(WebAuthnHelper):
    def register_complete(self, user: User, state: dict, data: dict):
        device = super().register_complete(user, state, data)

        # Create audit log, but skip notification for now as
        # the device name should be updated in the next request
        audit = AuditLog.objects.create(
            user,
            self.request,
            "twofactor-add",
            skip_notify=True,
            device=get_key_name(device),
        )

        # Store in session to possibly update after rename
        self.request.session[SESSION_WEBAUTHN_AUDIT] = audit.pk

        return device
