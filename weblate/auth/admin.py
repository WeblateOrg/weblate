# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy

from weblate.accounts.forms import FullNameField, UniqueEmailMixin, UniqueUsernameField
from weblate.accounts.utils import remove_user
from weblate.auth.data import ROLES
from weblate.auth.models import AuthenticatedHttpRequest, AutoGroup, Group, Role, User
from weblate.wladmin.models import WeblateModelAdmin

BUILT_IN_ROLES = {role[0] for role in ROLES}


def block_group_edit(obj: Group):
    """Whether to allow user editing of a group."""
    return obj and obj.internal


def block_role_edit(obj: Role):
    return obj and obj.name in BUILT_IN_ROLES


class AutoGroupChangeForm(forms.ModelForm):
    class Meta:
        model = AutoGroup
        fields = "__all__"  # noqa: DJ007

    def has_changed(self) -> bool:
        """
        Check whether data differs from initial.

        By always returning true even unchanged inlines will get validated and saved.
        """
        return True


class InlineAutoGroupAdmin(admin.TabularInline):
    model = AutoGroup
    form = AutoGroupChangeForm
    extra = 0

    def has_add_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Role)
class RoleAdmin(WeblateModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("permissions",)

    def has_change_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if block_role_edit(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if block_role_edit(obj):
            return False
        return super().has_delete_permission(request, obj)


class WeblateUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
        field_classes = {"username": UniqueUsernameField, "full_name": FullNameField}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["username"].valid = self.instance.username


class WeblateUserCreationForm(UserCreationForm, UniqueEmailMixin):
    validate_unique_mail = True

    class Meta:
        model = User
        fields = ("username", "email", "full_name")
        field_classes = {"username": UniqueUsernameField, "full_name": FullNameField}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class WeblateAuthAdmin(WeblateModelAdmin):
    def get_deleted_objects(self, objs, request: AuthenticatedHttpRequest):
        (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        ) = super().get_deleted_objects(objs, request)
        # Discard permission check for objects where deletion in admin is disabled
        # This behaves differently depending on Django version
        perms_needed.discard("profile")
        perms_needed.discard("User profile")
        perms_needed.discard("audit_log")
        perms_needed.discard("audit log")
        perms_needed.discard("Audit log entry")
        perms_needed.discard("verified_email")
        perms_needed.discard("verified email")
        perms_needed.discard("verified e-mail")
        perms_needed.discard("Verified email")
        perms_needed.discard("Verified e-mail")
        return deleted_objects, model_count, perms_needed, protected


@admin.register(User)
class WeblateUserAdmin(WeblateAuthAdmin, UserAdmin):
    """
    Custom UserAdmin class.

    Used to add listing of group membership and whether a user is active.
    """

    list_display = (
        "username",
        "email",
        "full_name",
        "user_groups",
        "is_active",
        "is_bot",
        "is_superuser",
    )
    search_fields = ("username", "full_name", "email")
    form = WeblateUserChangeForm
    add_form = WeblateUserCreationForm
    add_fieldsets = (
        (None, {"fields": ("username",)}),
        (gettext_lazy("Personal info"), {"fields": ("full_name", "email")}),
        (gettext_lazy("Authentication"), {"fields": ("password1", "password2")}),
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (gettext_lazy("Personal info"), {"fields": ("full_name", "email")}),
        (
            gettext_lazy("Permissions"),
            {"fields": ("is_active", "is_bot", "is_superuser", "groups")},
        ),
        (gettext_lazy("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_filter = ("is_superuser", "is_active", "is_bot", "groups")
    filter_horizontal = ("groups",)

    def user_groups(self, obj):
        """Display comma separated list of user groups."""
        return ",".join(obj.groups.values_list("name", flat=True))

    def action_checkbox(self, obj):
        if obj.is_anonymous:
            return ""
        return super().action_checkbox(obj)

    def has_delete_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if obj and obj.is_anonymous:
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request: AuthenticatedHttpRequest, obj) -> None:
        """Given a model instance delete it from the database."""
        remove_user(obj, request)

    def delete_queryset(self, request: AuthenticatedHttpRequest, queryset) -> None:
        """Given a queryset, delete it from the database."""
        for obj in queryset.iterator():
            self.delete_model(request, obj)


class GroupChangeForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = "__all__"  # noqa: DJ007

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "components" in self.fields:
            components = self.fields["components"]
            components.queryset = components.queryset.select_related("project")

    def clean(self) -> None:
        super().clean()
        has_componentlist = bool(self.cleaned_data["componentlists"])
        has_project = bool(self.cleaned_data["projects"])
        has_component = bool(self.cleaned_data["components"])
        if has_componentlist:
            fields = []
            if has_project:
                fields.append("projects")
            if has_component:
                fields.append("components")
            if fields:
                raise ValidationError(
                    {
                        field: gettext(
                            "This is not used when a component list is selected."
                        )
                        for field in fields
                    }
                )
        elif has_component and has_project:
            raise ValidationError(
                {"projects": gettext("This is not used when a component is selected.")}
            )


@admin.register(Group)
class WeblateGroupAdmin(WeblateAuthAdmin):
    save_as = True
    model = Group
    form = GroupChangeForm
    inlines = [InlineAutoGroupAdmin]
    search_fields = ("name", "defining_project__name")
    ordering = ("defining_project__name", "name")
    list_filter = ("internal", "project_selection", "language_selection")
    filter_horizontal = (
        "roles",
        "projects",
        "languages",
        "components",
        "componentlists",
    )
    list_display = ("name", "defining_project")

    new_obj: Group

    def action_checkbox(self, obj):
        if obj.internal:
            return ""
        return super().action_checkbox(obj)

    def has_delete_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if obj and obj.internal:
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request: AuthenticatedHttpRequest, obj=None):
        if block_group_edit(obj):
            return False
        return super().has_change_permission(request, obj)

    def save_model(self, request: AuthenticatedHttpRequest, obj, form, change) -> None:
        """
        Fix saving of automatic language/project selection, part 1.

        Stores saved object as an attribute to be used by save_related.
        """
        super().save_model(request, obj, form, change)
        self.new_obj = obj

    def save_related(
        self, request: AuthenticatedHttpRequest, form, formsets, change
    ) -> None:
        """
        Fix saving of automatic language/project selection, part 2.

        Uses stored attribute to save the model again. Saving triggers the automation
        and adjusts project/language selection according to the chosen value.
        """
        super().save_related(request, form, formsets, change)
        self.new_obj.save()
