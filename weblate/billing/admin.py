# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.contrib.admin import RelatedOnlyFieldListFilter
from django.utils.translation import gettext_lazy

from weblate.wladmin.models import WeblateModelAdmin

from .models import Billing, Invoice, Plan

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@admin.register(Plan)
class PlanAdmin(WeblateModelAdmin):
    list_display = (
        "name",
        "price",
        "limit_hosted_strings",
        "limit_strings",
        "limit_languages",
        "limit_projects",
        "display_limit_hosted_strings",
        "display_limit_strings",
        "display_limit_languages",
        "display_limit_projects",
        "public",
        "change_access_control",
    )
    ordering = ("name",)
    # ruff: ignore[mutable-class-default]
    prepopulated_fields = {
        "slug": ("name",),
    }
    list_filter = ("public", "change_access_control")


@admin.register(Billing)
class BillingAdmin(WeblateModelAdmin):
    list_display = (
        "list_projects",
        "workspace",
        "plan",
        "state",
        "removal",
        "expiry",
        "monthly_changes",
        "total_changes",
        "unit_count",
        "display_projects",
        "display_strings",
        "display_words",
        "display_languages",
        "in_limits",
        "in_display_limits",
        "paid",
        "last_invoice",
    )
    list_filter = ("plan", "state", "paid", "in_limits")
    search_fields = ("workspace__projects__name", "workspace__name", "customer_name")

    def get_queryset(self, request: AuthenticatedHttpRequest):
        return super().get_queryset(request).prefetch()

    @admin.display(description=gettext_lazy("Projects"))
    def list_projects(self, obj):
        if not obj.all_projects:
            return "none projects associated"
        return ",".join(project.name for project in obj.all_projects)

    def save_related(
        self, request: AuthenticatedHttpRequest, form, formsets, change
    ) -> None:
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Add owners as admin if there is none
        for project in obj.get_projects_queryset():
            group = project.defined_groups.get(name="Administration")
            if not group.user_set.exists():
                for user in obj.workspace.users_with_permission(
                    "workspace.edit_members"
                ):
                    user.add_team(request, group)


@admin.register(Invoice)
class InvoiceAdmin(WeblateModelAdmin):
    list_display = ("billing", "start", "end", "amount", "currency", "ref")
    list_filter = (
        "currency",
        ("billing__workspace__projects", RelatedOnlyFieldListFilter),
    )
    search_fields = ("billing__workspace__projects__name", "ref", "note")
    date_hierarchy = "end"
    ordering = ("billing", "-start")
    autocomplete_fields = ("billing",)
