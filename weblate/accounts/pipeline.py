# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
import time
import unicodedata

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import gettext
from django_otp import DEVICE_ID_SESSION_KEY
from social_core.exceptions import AuthAlreadyAssociated, AuthMissingParameter
from social_core.pipeline.partial import partial
from social_core.utils import PARTIAL_TOKEN_SESSION_NAME

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.accounts.notifications import send_notification_email
from weblate.accounts.templatetags.authnames import get_auth_name
from weblate.accounts.utils import (
    SESSION_SECOND_FACTOR_SOCIAL,
    SESSION_SECOND_FACTOR_USER,
    adjust_session_expiry,
    cycle_session_keys,
    invalidate_reset_codes,
)
from weblate.auth.models import Invitation, User
from weblate.trans.defines import FULLNAME_LENGTH
from weblate.utils import messages
from weblate.utils.ratelimit import reset_rate_limit
from weblate.utils.requests import request
from weblate.utils.validators import (
    CRUD_RE,
    USERNAME_MATCHER,
    EmailValidator,
    clean_fullname,
)

STRIP_MATCHER = re.compile(r"[^\w\s.@+-]")
CLEANUP_MATCHER = re.compile(r"[-\s]+")


class UsernameAlreadyAssociated(AuthAlreadyAssociated):
    pass


class EmailAlreadyAssociated(AuthAlreadyAssociated):
    pass


def get_github_emails(access_token):
    """Get real e-mail from GitHub."""
    response = request(
        "get",
        "https://api.github.com/user/emails",
        headers={"Authorization": f"token {access_token}"},
        timeout=10.0,
    )
    data = response.json()
    email = None
    primary = None
    public = None
    emails = []
    for entry in data:
        # Skip noreply e-mail only if we need deliverable e-mails
        if entry["email"].endswith("@users.noreply.github.com"):
            # Add E-Mail and set is_deliverable to false
            emails.append((entry["email"], False))
            continue
        # Skip not verified ones
        if not entry["verified"]:
            continue

        # Add E-Mail and set is_deliverable to true
        emails.append((entry["email"], True))
        if entry.get("visibility") == "public":
            # There is just one public mail, prefer it
            public = entry["email"]
            continue
        email = entry["email"]
        if entry["primary"]:
            primary = entry["email"]
    return public or primary or email, emails


@partial
def reauthenticate(
    strategy, backend, user: User, social, uid, weblate_action, **kwargs
):
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
        email, emails = get_github_emails(kwargs["response"]["access_token"])
        details["verified_emails"] = emails
        if email is not None:
            details["email"] = email

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


def send_validation(strategy, backend, code, partial_token) -> None:
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

    # Use None for user to enable linking by e-mail later for the registration
    AuditLog.objects.create(
        strategy.request.user if strategy.request.user.is_authenticated else None,
        strategy.request,
        "sent-email",
        email=code.email,
    )

    # Send actual confirmation
    send_notification_email(None, [code.email], template, info=url, context=context)


@partial
def password_reset(
    strategy,
    backend,
    user: User,
    social,
    details,
    weblate_action,
    current_partial,
    **kwargs,
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
        # Redirect to form to change password
        return redirect("password_reset")
    return None


@partial
def remove_account(
    strategy,
    backend,
    user: User,
    social,
    details,
    weblate_action: str,
    current_partial,
    **kwargs,
):
    """Set unusable password on reset."""
    if strategy.request is not None and user is not None and weblate_action == "remove":
        # Remove partial pipeline, we do not need it
        strategy.really_clean_partial_pipeline(current_partial.token)
        # Set short session expiry
        session = strategy.request.session
        session["remove_confirm"] = True
        # Reset rate limit to allow form submission
        reset_rate_limit("remove", strategy.request)
        # Redirect to the confirmation form
        return redirect("remove")
    return None


def verify_open(
    strategy,
    backend,
    user: User,
    weblate_action: str,
    invitation_link: Invitation | None,
    **kwargs,
) -> None:
    """Check whether it is possible to create new user."""
    # Ensure it's still same user (if sessions was kept as this is to avoid
    # completing authentication under different user than initiated it, with
    # new session, it will complete as new user)
    current_user = strategy.request.user.pk
    init_user = strategy.request.session.get("social_auth_user")
    if strategy.request.session.session_key and current_user != init_user:
        raise AuthMissingParameter(backend, "user")

    # Check whether registration is open
    if (
        not user
        and weblate_action not in {"reset", "remove"}
        and not invitation_link
        and (not settings.REGISTRATION_OPEN or settings.REGISTRATION_ALLOW_BACKENDS)
        and backend.name not in settings.REGISTRATION_ALLOW_BACKENDS
    ):
        raise AuthMissingParameter(backend, "disabled")


def cleanup_next(strategy, **kwargs):
    # This is mostly fix for lack of next validation in Python Social Auth
    # see https://github.com/python-social-auth/social-core/issues/62
    url = strategy.session_get("next")
    if url and not url_has_allowed_host_and_scheme(url, allowed_hosts=None):
        strategy.session_set("next", None)
    if url_has_allowed_host_and_scheme(kwargs.get("next", ""), allowed_hosts=None):
        return None
    return {"next": None}


def store_params(strategy, user: User, **kwargs):
    """Store Weblate specific parameters in the pipeline."""
    # Registering user
    registering_user = user.pk if user and user.is_authenticated else None

    # Pipeline action
    session = strategy.request.session
    if session.get("password_reset"):
        action = "reset"
    elif session.get("account_remove"):
        action = "remove"
    else:
        action = "activation"

    invitation = None
    if invitation_pk := session.get("invitation_link"):
        try:
            invitation = Invitation.objects.get(pk=invitation_pk)
        except Invitation.DoesNotExist:
            del session["invitation_link"]
            invitation_pk = None

    return {
        "weblate_action": action,
        "registering_user": registering_user,
        "weblate_expires": int(time.time() + settings.AUTH_TOKEN_VALID),
        "invitation_link": invitation,
        "invitation_pk": str(invitation_pk) if invitation_pk else None,
    }


def verify_username(strategy, backend, details, username, user=None, **kwargs) -> None:
    """
    Verify whether username is still free.

    It can happen that user has registered several times or other user has taken the
    username meanwhile.
    """
    if user or not username:
        return
    if User.objects.filter(username=username).exists():
        raise UsernameAlreadyAssociated(backend, "Username exists")
    return


def revoke_mail_code(strategy, details, **kwargs) -> None:
    """
    Remove old mail validation code for Python Social Auth.

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
    user: User,
    registering_user,
    weblate_action,
    weblate_expires,
    new_association,
    details,
    **kwargs,
) -> None:
    """Ensure the activation link is still."""
    # Didn't the link expire?
    if weblate_expires < time.time():
        raise AuthMissingParameter(backend, "expires")

    # We allow password reset for unauthenticated users
    if weblate_action == "reset":
        if strategy.request.user.is_authenticated:
            messages.warning(
                strategy.request,
                gettext("You can not complete password reset while signed in."),
            )
            messages.warning(
                strategy.request, gettext("The registration link has been invalidated.")
            )
            raise AuthMissingParameter(backend, "user")
        return

    # Add e-mail/register should stay on same user
    current_user = user.pk if user and user.is_authenticated else None

    if current_user != registering_user:
        if registering_user is None:
            messages.warning(
                strategy.request,
                gettext("You can not complete registration while signed in."),
            )
        else:
            messages.warning(
                strategy.request,
                gettext("You can confirm your registration only while signed in."),
            )
        messages.warning(
            strategy.request, gettext("The registration link has been invalidated.")
        )

        raise AuthMissingParameter(backend, "user")

    # Verify if this mail is not used on other accounts
    if new_association:
        if "email" not in details:
            raise AuthMissingParameter(backend, "email")
        same = VerifiedEmail.objects.filter(email__iexact=details["email"])
        if user:
            same = same.exclude(social__user=user)

        if not settings.REGISTRATION_REBIND and same.exists():
            AuditLog.objects.create(same[0].social.user, strategy.request, "connect")
            raise EmailAlreadyAssociated(backend, "E-mail exists")

        validator = EmailValidator()
        # This raises ValidationError
        validator(details["email"])


def store_email(strategy, backend, user: User, social, details, **kwargs) -> None:
    """Store verified e-mail."""
    # The email can be empty for some services
    if details.get("verified_emails"):
        # For some reasons tuples get converted to lists inside python social auth
        current = {tuple(verified) for verified in details["verified_emails"]}
        existing = set(social.verifiedemail_set.values_list("email", "is_deliverable"))
        for remove in existing - current:
            social.verifiedemail_set.filter(
                email=remove[0], is_deliverable=remove[1]
            ).delete()
        for add in current - existing:
            social.verifiedemail_set.create(email=add[0], is_deliverable=add[1])
    elif details.get("email"):
        verified, created = VerifiedEmail.objects.get_or_create(
            social=social, defaults={"email": details["email"]}
        )
        if (
            not created and verified.email != details["email"]
        ) or not verified.is_deliverable:
            verified.email = details["email"]
            verified.is_deliverable = True
            verified.save()


def handle_invite(
    strategy, backend, user: User, social, invitation_pk: str, **kwargs
) -> None:
    # Accept triggering invitation
    if invitation_pk:
        Invitation.objects.get(pk=invitation_pk).accept(strategy.request, user)
    # Merge possibly pending invitations for this e-mail address
    Invitation.objects.filter(email=user.email).update(user=user, email="")


def notify_connect(
    strategy,
    details,
    backend,
    user: User,
    social,
    weblate_action,
    new_association=False,
    is_new=False,
    **kwargs,
) -> None:
    """Notify about adding new link."""
    # Adjust possibly pending email confirmation audit logs
    AuditLog.objects.filter(
        user=None,
        activity="sent-email",
        params={"email": details["email"]},
    ).update(user=user)
    if user and not is_new and weblate_action != "reset":
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


def user_full_name(strategy, details, username, user=None, **kwargs) -> None:
    """Update user full name using data from provider."""
    if user and not user.full_name:
        full_name = details.get("fullname") or ""
        full_name = full_name.strip()

        if not full_name and ("first_name" in details or "last_name" in details):
            first_name = details.get("first_name") or ""
            last_name = details.get("last_name") or ""

            if first_name and first_name not in last_name:
                full_name = f"{first_name} {last_name}"
            elif first_name:
                full_name = first_name
            else:
                full_name = last_name

        if CRUD_RE.match(full_name):
            full_name = ""

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
    """
    Clean up username.

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


def cycle_session(strategy, user: User, *args, **kwargs) -> None:
    # Change key for current session and invalidate others
    cycle_session_keys(strategy.request, user)


def adjust_primary_mail(strategy, entries, user: User, *args, **kwargs) -> None:
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
        gettext(
            "Your e-mail no longer belongs to verified account, "
            "it has been changed to {0}."
        ).format(user.email),
    )


def notify_disconnect(strategy, backend, entries, user: User, **kwargs) -> None:
    """Store verified e-mail."""
    for social in entries:
        AuditLog.objects.create(
            user,
            strategy.request,
            "auth-disconnect",
            method=backend.name,
            name=social.uid,
        )


@partial
def second_factor(strategy, backend, user: User, current_partial, **kwargs):
    """Force authentication when adding new association."""
    if user.profile.has_2fa and DEVICE_ID_SESSION_KEY not in strategy.request.session:
        # Store session indication for second factor
        strategy.request.session[SESSION_SECOND_FACTOR_USER] = (user.id, "")
        strategy.request.session[SESSION_SECOND_FACTOR_SOCIAL] = True
        # Redirect to second factor login
        continue_url = "{}?partial_token={}".format(
            reverse("social:complete", args=(backend.name,)), current_partial.token
        )
        login_params = {"next": continue_url}
        login_url = reverse(
            "2fa-login", kwargs={"backend": user.profile.get_second_factor_type()}
        )
        return HttpResponseRedirect(f"{login_url}?{urlencode(login_params)}")
    return None
