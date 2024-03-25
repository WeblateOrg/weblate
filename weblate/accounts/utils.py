# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.authtoken.models import Token
from social_django.models import Code

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.auth.models import User
from weblate.trans.signals import user_pre_delete


def remove_user(user, request, **params) -> None:
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


def get_all_user_mails(user, entries=None, filter_deliverable=True):
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


def cycle_session_keys(request, user) -> None:
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


def adjust_session_expiry(request) -> None:
    """
    Adjust session expiry based on scope.

    - Set longer expiry for authenticated users.
    - Set short lived session for SAML authentication flow.
    """
    if "saml_only" not in request.session:
        next_url = request.POST.get("next", request.GET.get("next"))
        request.session["saml_only"] = next_url == "/idp/login/process/"

    if request.session["saml_only"]:
        # Short lived session for SAML authentication only
        request.session.set_expiry(60)
    else:
        request.session.set_expiry(settings.SESSION_COOKIE_AGE_AUTHENTICATED)
