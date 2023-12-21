# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.wladmin.models import WeblateModelAdmin


class AuditLogAdmin(WeblateModelAdmin):
    list_display = ["get_message", "user", "address", "user_agent", "timestamp"]
    search_fields = ["user__username", "user__email", "address", "activity"]
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def has_delete_permission(self, request, obj=None):
        return False


class ProfileAdmin(WeblateModelAdmin):
    list_display = ["user", "full_name", "language", "suggested", "translated"]
    search_fields = ["user__username", "user__email", "user__full_name"]
    list_filter = ["language"]
    filter_horizontal = ("languages", "secondary_languages", "watched")

    def has_delete_permission(self, request, obj=None):
        return False


class VerifiedEmailAdmin(WeblateModelAdmin):
    list_display = ("social", "provider", "email")
    search_fields = ("email", "social__user__username", "social__user__email")
    raw_id_fields = ("social",)
    ordering = ("email",)

    def has_delete_permission(self, request, obj=None):
        return False
