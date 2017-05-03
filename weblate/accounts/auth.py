# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import sys

from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.shortcuts import redirect
from django.core.urlresolvers import reverse
from django.db.models.signals import pre_save
from django.dispatch.dispatcher import receiver
from django.utils.translation import ugettext as _
from django.contrib.auth.backends import ModelBackend

import social_core.backends.email
from social_core.exceptions import AuthMissingParameter

from weblate.utils import messages
from weblate.utils.errors import report_error


def try_get_user(username):
    """Wrapper to get User object for authentication."""
    if '@' in username:
        return User.objects.get(email=username)
    else:
        return User.objects.get(username=username)


class EmailAuth(social_core.backends.email.EmailAuth):
    """Social auth handler to better report errors."""
    def auth_complete(self, *args, **kwargs):
        try:
            return super(EmailAuth, self).auth_complete(*args, **kwargs)
        except AuthMissingParameter as error:
            if error.parameter == 'email':
                messages.error(
                    self.strategy.request,
                    _(
                        'Failed to verify your registration! '
                        'Probably the verification token has expired. '
                        'Please try the registration again.'
                    )
                )
                report_error(
                    error, sys.exc_info(),
                    extra_data=self.data
                )
                return redirect(reverse('login'))
            raise


class WeblateUserBackend(ModelBackend):
    """Weblate authentication backend.

    It allows to control anonymous user permissions and to login using email.
    """
    def get_all_permissions(self, user_obj, obj=None):
        if ((not user_obj.is_active and not user_obj.is_anonymous)
                or obj is not None):
            return set()
        # pylint: disable=W0212
        if not hasattr(user_obj, '_perm_cache'):
            user_obj._perm_cache = self.get_user_permissions(user_obj)
            user_obj._perm_cache.update(self.get_group_permissions(user_obj))
        return user_obj._perm_cache

    def _get_permissions(self, user_obj, obj, from_name):
        """Return the permissions of `user_obj` from `from_name`.

        `from_name` can be either "group" or "user" to return permissions from
        `_get_group_permissions` or `_get_user_permissions` respectively.
        """
        if not user_obj.is_active and not user_obj.is_anonymous:
            return set()

        perm_cache_name = '_{0}_perm_cache'.format(from_name)
        if not hasattr(user_obj, perm_cache_name):
            if user_obj.is_superuser:
                perms = Permission.objects.all()
            else:
                perms = getattr(
                    self, '_get_{0}_permissions'.format(from_name)
                )(user_obj)
            perms = perms.values_list(
                'content_type__app_label', 'codename'
            ).order_by()
            setattr(
                user_obj,
                perm_cache_name,
                set("{0}.{1}".format(ct, name) for ct, name in perms)
            )
        return getattr(user_obj, perm_cache_name)

    def _get_group_permissions(self, user_obj):
        """Wrapper around _get_group_permissions to exclude groupacl

        We don't want these to be applied directly, they should work
        only using group matching rules."""
        user_groups = user_obj.groups.filter(groupacl=None)
        return Permission.objects.filter(group__in=user_groups)

    def authenticate(self, username=None, password=None, **kwargs):
        """Prohibit login for anonymous user and allows to login by email."""
        if username == settings.ANONYMOUS_USER_NAME or username is None:
            return None

        try:
            user = try_get_user(username)
            if user.check_password(password):
                return user
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return None

    def has_perm(self, user_obj, perm, obj=None):
        """Allow checking permissions for anonymous user as well."""
        if not user_obj.is_active and not user_obj.is_anonymous:
            return False
        return perm in self.get_all_permissions(user_obj, obj)


@receiver(pre_save, sender=User)
def disable_anon_user_password_save(sender, **kwargs):
    """Block setting password for anonymous user."""
    instance = kwargs['instance']
    if (instance.username == settings.ANONYMOUS_USER_NAME and
            instance.has_usable_password()):
        raise ValueError('Anonymous user can not have usable password!')
