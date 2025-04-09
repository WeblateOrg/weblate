# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp_webauthn.helpers import WebAuthnHelper
from django_otp_webauthn.models import WebAuthnCredential
from rest_framework.authtoken.models import Token
from social_django.models import Code

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.trans.signals import user_pre_delete

if TYPE_CHECKING:
    from django_otp.models import Device

SESSION_WEBAUTHN_AUDIT = "weblate:second_factor:webauthn_audit_log"
SESSION_SECOND_FACTOR_USER = "weblate:second_factor:user"
SESSION_SECOND_FACTOR_SOCIAL = "weblate:second_factor:social"
SESSION_SECOND_FACTOR_TOTP = "weblate:second_factor:totp_key"

DeviceType = Literal["totp", "webauthn", "recovery"]


def remove_user(user: User, request: AuthenticatedHttpRequest, **params) -> None:
    """Remove user account."""
    # Send signal (to commit any pending changes)
    user_pre_delete.send(instance=user, sender=user.__class__)

    # Store activity log and notify
    AuditLog.objects.create(user, request, "removed", **params)

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
    Token.objects.filter(user=user).delete()


def lock_user(
    user: User,
    reason: Literal["locked", "admin-locked"],
    request: AuthenticatedHttpRequest | None = None,
):
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
    emails.discard(None)
    emails.discard("")
    return emails


def invalidate_reset_codes(user=None, entries=None, emails=None) -> None:
    """Invalidate email activation codes for an user."""
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
    # Cycle session key
    update_session_auth_hash(request, user)


def adjust_session_expiry(
    request: AuthenticatedHttpRequest, *, is_login: bool = True
) -> None:
    """
    Adjust session expiry based on scope.

    - Set longer expiry for authenticated users.
    - Set short lived session for SAML authentication flow.
    """
    if "saml_only" not in request.session:
        if is_login:
            next_url = request.POST.get("next", request.GET.get("next"))
            request.session["saml_only"] = next_url == "/idp/login/process/"
        else:
            request.session["saml_only"] = False

    if request.session["saml_only"]:
        # Short lived session for SAML authentication only
        request.session.set_expiry(60)
    else:
        request.session.set_expiry(settings.SESSION_COOKIE_AGE_AUTHENTICATED)


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
