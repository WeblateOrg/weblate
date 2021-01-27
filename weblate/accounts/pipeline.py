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
import time
import unicodedata

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from social_core.exceptions import AuthAlreadyAssociated, AuthMissingParameter
from social_core.pipeline.partial import partial
from social_core.utils import PARTIAL_TOKEN_SESSION_NAME

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.accounts.notifications import send_notification_email
from weblate.accounts.templatetags.authnames import get_auth_name
from weblate.accounts.utils import (
    adjust_session_expiry,
    cycle_session_keys,
    invalidate_reset_codes,
)
from weblate.auth.models import User, get_anonymous
from weblate.trans.defines import FULLNAME_LENGTH
from weblate.utils import messages
from weblate.utils.requests import request
from weblate.utils.validators import USERNAME_MATCHER, clean_fullname

STRIP_MATCHER = re.compile(r"[^\w\s.@+-]")
CLEANUP_MATCHER = re.compile(r"[-\s]+")


class UsernameAlreadyAssociated(AuthAlreadyAssociated):
    pass


class EmailAlreadyAssociated(AuthAlreadyAssociated):
    pass


def get_github_email(access_token):
    """Get real e-mail from GitHub."""
    response = request(
        "get",
        "https://api.github.com/user/emails",
        headers={"Authorization": f"token {access_token}"},
        timeout=10.0,
    )
    data = response.json()
    email = None
    for entry in data:
        # Skip not verified ones
        if not entry["verified"]:
            continue
        email = entry["email"]
        if entry["primary"]:
            break
    return email


@partial
def reauthenticate(strategy, backend, user, social, uid, weblate_action, **kwargs):
    """Force authentication when adding new association."""
    session = strategy.request.session
    if session.pop("reauthenticate_done", False):
        return None
    if weblate_action != "activation":
        return None
    if user and not social and user.has_usable_password():
        session["reauthenticate"] = {
            "backend": backend.name,
            "backend_verbose": str(get_auth_name(backend.name)),
            "uid": uid,
            "user_pk": user.pk,
        }
        return redirect("confirm")
    return None


@partial
def require_email(backend, details, weblate_action, user=None, is_new=False, **kwargs):
    """Force entering e-mail for backends which don't provide it."""
    if backend.name == "github":
        email = get_github_email(kwargs["response"]["access_token"])
        if email is not None:
            details["email"] = email
        if details.get("email", "").endswith("@users.noreply.github.com"):
            del details["email"]

    # Remove any pending e-mail validation codes
    if details.get("email") and backend.name == "email":
        invalidate_reset_codes(emails=(details["email"],))
        # Remove all account reset codes
        if user and weblate_action == "reset":
            invalidate_reset_codes(user=user)

    if user and user.email:
        # Force validation of new e-mail address
        if backend.name == "email":
            return {"is_new": True}

        return None

    if is_new and not details.get("email"):
        raise AuthMissingParameter(backend, "email")
    return None


def send_validation(strategy, backend, code, partial_token):
    """Send verification e-mail."""
    # We need to have existing session
    session = strategy.request.session
    if not session.session_key:
        session.create()
    session["registration-email-sent"] = True

    url = "{}?verification_code={}&partial_token={}".format(
        reverse("social:complete", args=(backend.name,)), code.code, partial_token
    )

    context = {"url": url, "validity": settings.AUTH_TOKEN_VALID // 3600}

    template = "activation"
    if session.get("password_reset"):
        template = "reset"
    elif session.get("account_remove"):
        template = "remove"
    elif session.get("user_invite"):
        template = "invite"
        context.update(session["invitation_context"])

    # Create audit log, it might be for anonymous at this point for new registrations
    AuditLog.objects.create(
        strategy.request.user,
        strategy.request,
        "sent-email",
        email=code.email,
    )

    # Send actual confirmation
    send_notification_email(None, [code.email], template, info=url, context=context)


@partial
def password_reset(
    strategy, backend, user, social, details, weblate_action, current_partial, **kwargs
):
    """Set unusable password on reset."""
    if strategy.request is not None and user is not None and weblate_action == "reset":
        AuditLog.objects.create(
            user,
            strategy.request,
            "reset",
            method=backend.name,
            name=social.uid,
            password=user.password,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        # Remove partial pipeline, we do not need it
        strategy.really_clean_partial_pipeline(current_partial.token)
        session = strategy.request.session
        # Store user ID
        session["perform_reset"] = user.pk
        # Set short session expiry
        session.set_expiry(90)
        # Redirect to form to change password
        return redirect("password_reset")
    return None


@partial
def remove_account(
    strategy, backend, user, social, details, weblate_action, current_partial, **kwargs
):
    """Set unusable password on reset."""
    if strategy.request is not None and user is not None and weblate_action == "remove":
        # Remove partial pipeline, we do not need it
        strategy.really_clean_partial_pipeline(current_partial.token)
        # Set short session expiry
        session = strategy.request.session
        session.set_expiry(90)
        session["remove_confirm"] = True
        # Redirect to form to change password
        return redirect("remove")
    return None


def verify_open(strategy, backend, user, weblate_action, **kwargs):
    """Check whether it is possible to create new user."""
    # Check whether registration is open
    if (
        not user
        and weblate_action not in ("reset", "remove", "invite")
        and (not settings.REGISTRATION_OPEN or settings.REGISTRATION_ALLOW_BACKENDS)
        and backend.name not in settings.REGISTRATION_ALLOW_BACKENDS
    ):
        raise AuthMissingParameter(backend, "disabled")

    # Ensure it's still same user (if sessions was kept as this is to avoid
    # completing authentication under diferent user than initiated it, with
    # new session, it will complete as new user)
    current_user = strategy.request.user.pk
    init_user = strategy.request.session.get("social_auth_user")
    if strategy.request.session.session_key and current_user != init_user:
        raise AuthMissingParameter(backend, "user")


def cleanup_next(strategy, **kwargs):
    # This is mostly fix for lack of next validation in Python Social Auth
    # see https://github.com/python-social-auth/social-core/issues/62
    url = strategy.session_get("next")
    if url and not url_has_allowed_host_and_scheme(url, allowed_hosts=None):
        strategy.session_set("next", None)
    if url_has_allowed_host_and_scheme(kwargs.get("next", ""), allowed_hosts=None):
        return None
    return {"next": None}


def store_params(strategy, user, **kwargs):
    """Store Weblate specific parameters in the pipeline."""
    # Registering user
    if user and user.is_authenticated:
        registering_user = user.pk
    else:
        registering_user = None

    # Pipeline action
    session = strategy.request.session
    if session.get("password_reset"):
        action = "reset"
    elif session.get("account_remove"):
        action = "remove"
    elif session.get("user_invite"):
        action = "invite"
    else:
        action = "activation"

    return {
        "weblate_action": action,
        "registering_user": registering_user,
        "weblate_expires": int(time.time() + settings.AUTH_TOKEN_VALID),
    }


def verify_username(strategy, backend, details, username, user=None, **kwargs):
    """Verified whether username is still free.

    It can happen that user has registered several times or other user has taken the
    username meanwhile.
    """
    if user or not username:
        return
    if User.objects.filter(username=username).exists():
        raise UsernameAlreadyAssociated(backend, "Username exists")
    return


def revoke_mail_code(strategy, details, **kwargs):
    """Remove old mail validation code for Python Social Auth.

    PSA keeps them around, but we really don't need them again.
    """
    data = strategy.request_data()
    if "email" in details and details["email"] and "verification_code" in data:
        try:
            code = strategy.storage.code.objects.get(
                code=data["verification_code"], email=details["email"], verified=True
            )
            code.delete()
        except strategy.storage.code.DoesNotExist:
            return


def ensure_valid(
    strategy,
    backend,
    user,
    registering_user,
    weblate_action,
    weblate_expires,
    new_association,
    details,
    **kwargs,
):
    """Ensure the activation link is still."""
    # Didn't the link expire?
    if weblate_expires < time.time():
        raise AuthMissingParameter(backend, "expires")

    # We allow password reset for unauthenticated users
    if weblate_action == "reset":
        if strategy.request.user.is_authenticated:
            messages.warning(
                strategy.request,
                _("You can not complete password reset while signed in."),
            )
            messages.warning(
                strategy.request, _("The registration link has been invalidated.")
            )
            raise AuthMissingParameter(backend, "user")
        return

    # Add e-mail/register should stay on same user
    if user and user.is_authenticated:
        current_user = user.pk
    else:
        current_user = None

    if current_user != registering_user:
        if registering_user is None:
            messages.warning(
                strategy.request,
                _("You can not complete registration while signed in."),
            )
        else:
            messages.warning(
                strategy.request,
                _("You can confirm your registration only while signed in."),
            )
        messages.warning(
            strategy.request, _("The registration link has been invalidated.")
        )

        raise AuthMissingParameter(backend, "user")

    # Verify if this mail is not used on other accounts
    if new_association:
        if "email" not in details:
            raise AuthMissingParameter(backend, "email")
        same = VerifiedEmail.objects.filter(email__iexact=details["email"])
        if user:
            same = same.exclude(social__user=user)

        if same.exists():
            AuditLog.objects.create(same[0].social.user, strategy.request, "connect")
            raise EmailAlreadyAssociated(backend, "E-mail exists")


def store_email(strategy, backend, user, social, details, **kwargs):
    """Store verified e-mail."""
    # The email can be empty for some services
    if details.get("email"):
        verified, created = VerifiedEmail.objects.get_or_create(
            social=social, defaults={"email": details["email"]}
        )
        if not created and verified.email != details["email"]:
            verified.email = details["email"]
            verified.save()


def notify_connect(
    strategy,
    details,
    backend,
    user,
    social,
    new_association=False,
    is_new=False,
    **kwargs,
):
    """Notify about adding new link."""
    # Adjust possibly pending email confirmation audit logs
    AuditLog.objects.filter(
        user=get_anonymous(),
        activity="sent-email",
        params={"email": details["email"]},
    ).update(user=user)
    if user and not is_new:
        if new_association:
            action = "auth-connect"
        else:
            action = "login"
            adjust_session_expiry(strategy.request)
        AuditLog.objects.create(
            user,
            strategy.request,
            action,
            method=backend.name,
            name=social.uid,
        )
    # Remove partial pipeline
    session = strategy.request.session
    if PARTIAL_TOKEN_SESSION_NAME in session:
        strategy.really_clean_partial_pipeline(session[PARTIAL_TOKEN_SESSION_NAME])


def user_full_name(strategy, details, username, user=None, **kwargs):
    """Update user full name using data from provider."""
    if user and not user.full_name:
        full_name = details.get("fullname", "").strip()

        if not full_name and ("first_name" in details or "last_name" in details):
            first_name = details.get("first_name", "")
            last_name = details.get("last_name", "")

            if first_name and first_name not in last_name:
                full_name = f"{first_name} {last_name}"
            elif first_name:
                full_name = first_name
            else:
                full_name = last_name

        if not full_name and username:
            full_name = username

        if not full_name and user.username:
            full_name = user.username

        full_name = clean_fullname(full_name)

        # The User model limit is 150 chars
        if len(full_name) > FULLNAME_LENGTH:
            full_name = full_name[:FULLNAME_LENGTH]

        if full_name:
            user.full_name = full_name
            strategy.storage.user.changed(user)


def slugify_username(value):
    """Clean up username.

    This is based on Django slugify with exception of lowercasing

    - Converts to ascii
    - Removes not wanted chars
    - Merges whitespaces and - into single -
    """
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )

    # Return username if it matches our standards
    if USERNAME_MATCHER.match(value):
        return value

    value = STRIP_MATCHER.sub("", value).strip().lstrip(".")
    return CLEANUP_MATCHER.sub("-", value)


def cycle_session(strategy, user, *args, **kwargs):
    # Change key for current session and invalidate others
    cycle_session_keys(strategy.request, user)


def adjust_primary_mail(strategy, entries, user, *args, **kwargs):
    """Fix primary mail on disconnect."""
    # Remove pending verification codes
    invalidate_reset_codes(user=user, entries=entries)

    # Check remaining verified mails
    verified = VerifiedEmail.objects.filter(social__user=user).exclude(
        social__in=entries
    )
    if verified.filter(email=user.email).exists():
        return

    user.email = verified[0].email
    user.save()
    messages.warning(
        strategy.request,
        _(
            "Your e-mail no longer belongs to verified account, "
            "it has been changed to {0}."
        ).format(user.email),
    )


def notify_disconnect(strategy, backend, entries, user, **kwargs):
    """Store verified e-mail."""
    for social in entries:
        AuditLog.objects.create(
            user,
            strategy.request,
            "auth-disconnect",
            method=backend.name,
            name=social.uid,
        )
