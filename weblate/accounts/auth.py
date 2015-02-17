# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from weblate.appsettings import ANONYMOUS_USER_NAME

from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch.dispatcher import receiver

from django.contrib.auth.backends import ModelBackend


class WeblateUserBackend(ModelBackend):
    '''
    Authentication backend which allows to control anonymous user
    permissions and to login using email.
    '''

    def get_all_permissions(self, user_obj, obj=None):
        '''
        Overrides get_all_permissions for anonymous users
        to pass permissions of defined user.
        '''
        if user_obj.is_anonymous():
            # Need to access private attribute, pylint: disable=W0212
            if not hasattr(user_obj, '_perm_cache'):
                anon_user = User.objects.get(username=ANONYMOUS_USER_NAME)
                anon_user.is_active = True
                user_obj._perm_cache = self.get_all_permissions(anon_user, obj)
            return user_obj._perm_cache
        return super(WeblateUserBackend, self).get_all_permissions(
            user_obj, obj
        )

    def authenticate(self, username=None, password=None, **kwargs):
        '''
        Prohibits login for anonymous user and allows to login by email.
        '''
        if username == ANONYMOUS_USER_NAME:
            return False

        if '@' in username:
            kwargs = {'email': username}
        else:
            kwargs = {'username': username}
        try:
            user = User.objects.get(**kwargs)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None

    def has_perm(self, user_obj, perm, obj=None):
        '''
        Allows checking permissions for anonymous user as well.
        '''
        if not user_obj.is_active and not user_obj.is_anonymous:
            return False
        return perm in self.get_all_permissions(user_obj, obj)


@receiver(pre_save, sender=User)
def disable_anon_user_password_save(sender, **kwargs):
    '''
    Blocks setting password for anonymous user.
    '''
    instance = kwargs['instance']
    if (instance.username == ANONYMOUS_USER_NAME and
            instance.has_usable_password()):
        raise ValueError('Anonymous user can not have usable password!')
