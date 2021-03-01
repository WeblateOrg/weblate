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

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from weblate.accounts.forms import FullNameField, UniqueEmailMixin, UniqueUsernameField
from weblate.accounts.utils import remove_user
from weblate.auth.data import ROLES
from weblate.auth.models import AutoGroup, Group, User
from weblate.wladmin.models import WeblateModelAdmin

BUILT_IN_ROLES = {role[0] for role in ROLES}


def block_group_edit(obj):
    """Whether to allo user editing of an group."""
    return obj and obj.internal and "@" in obj.name


def block_role_edit(obj):
    return obj and obj.name in BUILT_IN_ROLES


class InlineAutoGroupAdmin(admin.TabularInline):
    model = AutoGroup
    extra = 0

    def has_add_permission(self, request, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_delete_permission(request, obj)


class RoleAdmin(WeblateModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("permissions",)

    def has_change_permission(self, request, obj=None):
        if block_role_edit(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if block_role_edit(obj):
            return False
        return super().has_delete_permission(request, obj)


class WeblateUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {"username": UniqueUsernameField, "full_name": FullNameField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["username"].valid = self.instance.username


class WeblateUserCreationForm(UserCreationForm, UniqueEmailMixin):
    validate_unique_mail = True

    class Meta:
        model = User
        fields = ("username", "email", "full_name")
        field_classes = {"username": UniqueUsernameField, "full_name": FullNameField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class WeblateAuthAdmin(WeblateModelAdmin):
    def get_deleted_objects(self, objs, request):
        (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        ) = super().get_deleted_objects(objs, request)
        # Discard permission check for objects where deletion in admin is disabled
        perms_needed.discard("profile")
        perms_needed.discard("audit_log")
        perms_needed.discard("audit log")
        perms_needed.discard("verified_email")
        perms_needed.discard("verified email")
        return deleted_objects, model_count, perms_needed, protected


class WeblateUserAdmin(WeblateAuthAdmin, UserAdmin):
    """Custom UserAdmin class.

    Used to add listing of group membership and whether user is active.
    """

    list_display = (
        "username",
        "email",
        "full_name",
        "user_groups",
        "is_active",
        "is_superuser",
    )
    search_fields = ("username", "full_name", "email")
    form = WeblateUserChangeForm
    add_form = WeblateUserCreationForm
    add_fieldsets = (
        (None, {"fields": ("username",)}),
        (_("Personal info"), {"fields": ("full_name", "email")}),
        (_("Authentication"), {"fields": ("password1", "password2")}),
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("full_name", "email")}),
        (_("Permissions"), {"fields": ("is_active", "is_superuser", "groups")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_filter = ("is_superuser", "is_active", "groups")
    filter_horizontal = ("groups",)

    def user_groups(self, obj):
        """Display comma separated list of user groups."""
        return ",".join(g.name for g in obj.groups.iterator())

    def action_checkbox(self, obj):
        if obj.is_anonymous:
            return ""
        return super().action_checkbox(obj)

    action_checkbox.short_description = mark_safe(
        '<input type="checkbox" id="action-toggle" />'
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_anonymous:
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        """Given a model instance delete it from the database."""
        remove_user(obj, request)

    def delete_queryset(self, request, queryset):
        """Given a queryset, delete it from the database."""
        for obj in queryset.iterator():
            self.delete_model(request, obj)


class WeblateGroupAdmin(WeblateAuthAdmin):
    save_as = True
    model = Group
    inlines = [InlineAutoGroupAdmin]
    search_fields = ("name",)
    ordering = ("name",)
    list_filter = ("internal", "project_selection", "language_selection")
    filter_horizontal = ("roles", "projects", "languages")

    new_obj = None

    def action_checkbox(self, obj):
        if obj.internal:
            return ""
        return super().action_checkbox(obj)

    action_checkbox.short_description = mark_safe(
        '<input type="checkbox" id="action-toggle" />'
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.internal:
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Fix saving of automatic language/project selection, part 1.

        Stores saved object as an attribute to be used by save_related.
        """
        super().save_model(request, obj, form, change)
        self.new_obj = obj

    def save_related(self, request, form, formsets, change):
        """Fix saving of automatic language/project selection, part 2.

        Uses stored attribute to save the model again. Saving triggers the automation
        and adjusts project/language selection according to the chosen value.
        """
        super().save_related(request, form, formsets, change)
        self.new_obj.save()
