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

import os

from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from rest_framework.authtoken.models import Token
from social_django.models import Code

from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.auth.models import User
from weblate.trans.signals import user_pre_delete


def remove_user(user, request):
    """Remove user account."""
    # Send signal (to commit any pending changes)
    user_pre_delete.send(instance=user, sender=user.__class__)

    # Store activity log and notify
    AuditLog.objects.create(user, request, "removed")

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

    # Remove user translation memory
    user.memory_set.all().delete()

    # Cleanup profile
    profile = user.profile
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
    Token.objects.filter(user=request.user).delete()


def get_all_user_mails(user, entries=None):
    """Return all verified mails for user."""
    kwargs = {"social__user": user}
    if entries:
        kwargs["social__in"] = entries
    emails = set(VerifiedEmail.objects.filter(**kwargs).values_list("email", flat=True))
    emails.add(user.email)
    return emails


def invalidate_reset_codes(user=None, entries=None, emails=None):
    """Invalidate email activation codes for an user."""
    if emails is None:
        emails = get_all_user_mails(user, entries)
    Code.objects.filter(email__in=emails).delete()


def cycle_session_keys(request, user):
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


def adjust_session_expiry(request):
    """Set longer expiry for authenticated users."""
    request.session.set_expiry(settings.SESSION_COOKIE_AGE_AUTHENTICATED)
