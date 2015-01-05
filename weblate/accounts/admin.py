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

from django.contrib import admin
from weblate.accounts.models import Profile, VerifiedEmail
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User


class ProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'full_name', 'language', 'suggested', 'translated'
    ]
    search_fields = [
        'user__username', 'user__email', 'user__first_name'
    ]
    list_filter = ['language']

admin.site.register(Profile, ProfileAdmin)


class VerifiedEmailAdmin(admin.ModelAdmin):
    list_display = ('social', 'email')
    search_fields = ('email', )
    raw_id_fields = ('social',)

admin.site.register(VerifiedEmail, VerifiedEmailAdmin)


class WeblateUserAdmin(UserAdmin):
    '''
    Custom UserAdmin to add listing of group membership and whether user is
    active.
    '''
    list_display = UserAdmin.list_display + ('is_active', 'user_groups', 'id')
    list_filter = UserAdmin.list_filter + ('groups',)

    def user_groups(self, obj):
        """
        Get group, separate by comma, and display empty string if user has
        no group
        """
        return ','.join([g.name for g in obj.groups.all()])

# Need to unregister orignal Django UserAdmin
admin.site.unregister(User)
# Set WeblateUserAdmin to handle User in admin interface
admin.site.register(User, WeblateUserAdmin)
