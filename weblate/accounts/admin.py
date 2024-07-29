# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from weblate.wladmin.models import WeblateModelAdmin

from .models import AuditLog, Profile, VerifiedEmail

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@admin.register(AuditLog)
class AuditLogAdmin(WeblateModelAdmin):
    list_display = ["get_message", "user", "address", "user_agent", "timestamp"]
    search_fields = ["user__username", "user__email", "address", "activity"]
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def has_delete_permission(
        self, request: AuthenticatedHttpRequest, obj=None
    ) -> bool:
        return False

    def has_add_permission(self, request: AuthenticatedHttpRequest, obj=None) -> bool:
        return False


@admin.register(Profile)
class ProfileAdmin(WeblateModelAdmin):
    list_display = ["user", "full_name", "language", "suggested", "translated"]
    search_fields = ["user__username", "user__email", "user__full_name"]
    list_filter = ["language"]
    filter_horizontal = ("languages", "secondary_languages", "watched")

    def has_delete_permission(
        self, request: AuthenticatedHttpRequest, obj=None
    ) -> bool:
        return False

    def has_add_permission(self, request: AuthenticatedHttpRequest, obj=None) -> bool:
        return False


@admin.register(VerifiedEmail)
class VerifiedEmailAdmin(WeblateModelAdmin):
    list_display = ("social", "provider", "email")
    search_fields = ("email", "social__user__username", "social__user__email")
    raw_id_fields = ("social",)
    ordering = ("email",)

    def has_delete_permission(
        self, request: AuthenticatedHttpRequest, obj=None
    ) -> bool:
        return False
