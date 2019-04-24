# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import os
import binascii

from social_django.models import Code

from weblate.auth.models import User
from weblate.trans.signals import user_pre_delete
from weblate.accounts.models import VerifiedEmail, AuditLog


def remove_user(user, request):
    """Remove user account."""

    # Send signal (to commit any pending changes)
    user_pre_delete.send(instance=user, sender=user.__class__)

    # Store activity log and notify
    AuditLog.objects.create(user, request, 'removed')

    # Remove any email validation codes
    invalidate_reset_codes(user)

    # Change username
    user.username = 'deleted-{0}'.format(user.pk)
    user.email = 'noreply+{}@weblate.org'.format(user.pk)
    while User.objects.filter(username=user.username).exists():
        user.username = 'deleted-{0}-{1}'.format(
            user.pk,
            binascii.b2a_hex(os.urandom(5))
        )
    while User.objects.filter(email=user.email).exists():
        user.email = 'noreply+{0}-{1}@weblate.org'.format(
            user.pk,
            binascii.b2a_hex(os.urandom(5))
        )

    # Remove user information
    user.full_name = 'Deleted User'

    # Disable the user
    user.is_active = False
    user.set_unusable_password()
    user.save()

    # Remove all social auth associations
    user.social_auth.all().delete()

    # Remove user from all groups
    user.groups.clear()


def get_all_user_mails(user, entries=None):
    """Return all verified mails for user."""
    verified = VerifiedEmail.objects.filter(social__user=user)
    if entries:
        verified = verified.filter(social__in=entries)
    emails = set(verified.values_list('email', flat=True))
    emails.add(user.email)
    return emails


def invalidate_reset_codes(user=None, entries=None, emails=None):
    """Invalidate email activation codes for an user."""
    if emails is None:
        emails = get_all_user_mails(user, entries)
    Code.objects.filter(email__in=emails).delete()
