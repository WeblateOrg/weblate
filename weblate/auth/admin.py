# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

from weblate.accounts.forms import (
    UniqueEmailMixin, FullNameField, UsernameField,
)
from weblate.auth.models import User, Group, AutoGroup
from weblate.wladmin.models import WeblateModelAdmin


class AutoGroupAdmin(WeblateModelAdmin):
    list_display = ('group', 'match')


class InlineAutoGroupAdmin(admin.TabularInline):
    model = AutoGroup
    extra = 0


class RoleAdmin(WeblateModelAdmin):
    list_display = ('name',)
    filter_horizontal = ('permissions',)


class WeblateUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'
        field_classes = {
            'username': UsernameField,
            'full_name': FullNameField,
        }

    def __init__(self, *args, **kwargs):
        super(WeblateUserChangeForm, self).__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['username'].valid = self.instance.username


class WeblateUserCreationForm(UserCreationForm, UniqueEmailMixin):
    validate_unique_mail = True

    class Meta(object):
        model = User
        fields = ('username', 'email', 'full_name')
        field_classes = {
            'username': UsernameField,
            'full_name': FullNameField,
        }

    def __init__(self, *args, **kwargs):
        super(WeblateUserCreationForm, self).__init__(*args, **kwargs)
        self.fields['email'].required = True


class WeblateUserAdmin(UserAdmin):
    """Custom UserAdmin class.

    Used to add listing of group membership and whether user is active.
    """
    list_display = (
        'username', 'email', 'full_name', 'user_groups', 'is_active',
        'is_superuser',
    )
    search_fields = ('username', 'full_name', 'email')
    form = WeblateUserChangeForm
    add_form = WeblateUserCreationForm
    add_fieldsets = (
        (None, {'fields': ('username',)}),
        (_('Personal info'), {'fields': ('full_name', 'email')}),
        (_('Authentication'), {'fields': ('password1', 'password2')}),
    )
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('full_name', 'email')}),
        (_('Permissions'), {'fields': (
            'is_active', 'is_superuser',
            'groups',
        )}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    list_filter = ('is_superuser', 'is_active', 'groups')
    filter_horizontal = ('groups',)

    def user_groups(self, obj):
        """Display comma separated list of user groups."""
        return ','.join([g.name for g in obj.groups.all()])

    def action_checkbox(self, obj):
        if obj.is_anonymous:
            return ''
        return super(WeblateUserAdmin, self).action_checkbox(obj)
    action_checkbox.short_description = mark_safe(
        '<input type="checkbox" id="action-toggle" />'
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_anonymous:
            return False
        return super(WeblateUserAdmin, self).has_delete_permission(
            request, obj
        )


class WeblateGroupAdmin(WeblateModelAdmin):
    save_as = True
    model = Group
    inlines = [InlineAutoGroupAdmin]
    search_fields = ('name',)
    ordering = ('name',)
    list_filter = ('internal', 'project_selection', 'language_selection')
    filter_horizontal = ('roles', 'projects', 'languages')

    new_obj = None

    def action_checkbox(self, obj):
        if obj.internal:
            return ''
        return super(WeblateGroupAdmin, self).action_checkbox(obj)
    action_checkbox.short_description = mark_safe(
        '<input type="checkbox" id="action-toggle" />'
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.internal:
            return False
        return super(WeblateGroupAdmin, self).has_delete_permission(
            request, obj
        )

    def save_model(self, request, obj, form, change):
        """Fix saving of automatic language/project selection, part 1

        Stores saved object as an attribute to be used by save_related.
        """
        super(WeblateGroupAdmin, self).save_model(request, obj, form, change)
        self.new_obj = obj

    def save_related(self, request, form, formsets, change):
        """Fix saving of automatic language/project selection, part 2

        Uses stored attribute to save the model again. Saving triggers the
        automation and adjusts project/langauge selection according to
        the chosen value.
        """
        super(WeblateGroupAdmin, self).save_related(
            request, form, formsets, change
        )
        self.new_obj.save()
