# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from django.contrib.auth.models import User, UNUSABLE_PASSWORD
from django.db.models.signals import pre_save
from django.dispatch.dispatcher import receiver

from django.contrib.auth.backends import ModelBackend


class AnonymousUserBackend(ModelBackend):
    '''
    Authentication backend which allows to control anonymous user
    permissions.
    '''

    def get_all_permissions(self, user_obj):
        '''
        Overrides get_all_permissions for anonymous users
        to pass permissions of defined user.
        '''
        if user_obj.is_anonymous():
            if not hasattr(user_obj, '_perm_cache'):
                anon_user = User.objects.get(username=ANONYMOUS_USER_NAME)
                user_obj._perm_cache = self.get_all_permissions(anon_user)
            return user_obj._perm_cache
        return super(AnonymousUserBackend, self).get_all_permissions(user_obj)

    def authenticate(self, username=None, password=None):
        '''
        Prohibits login for anonymous user.
        '''
        if username == ANONYMOUS_USER_NAME:
            return False
        return super(AnonymousUserBackend, self).authenticate(
            username, password
        )

    def has_perm(self, user_obj, perm):
        '''
        Allows checking permissions for anonymous user as well.
        '''
        if not user_obj.is_active and not user_obj.is_anonymous:
            return False
        return perm in self.get_all_permissions(user_obj)


@receiver(pre_save, sender=User)
def disable_anon_user_password_save(sender, **kwargs):
    '''
    Blocks setting password for anonymous user.
    '''
    instance = kwargs['instance']
    if (instance.username == ANONYMOUS_USER_NAME
            and instance.password != UNUSABLE_PASSWORD):
        raise ValueError('Anonymous user can not have usable password!')
