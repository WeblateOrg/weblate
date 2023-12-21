# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib import admin
from django.contrib.admin import RelatedOnlyFieldListFilter
from django.utils.translation import gettext_lazy

from weblate.wladmin.models import WeblateModelAdmin


class PlanAdmin(WeblateModelAdmin):
    list_display = (
        "name",
        "price",
        "limit_strings",
        "limit_languages",
        "limit_projects",
        "display_limit_strings",
        "display_limit_languages",
        "display_limit_projects",
    )
    ordering = ["price"]
    prepopulated_fields = {"slug": ("name",)}


def format_user(obj):
    return f"{obj.username}: {obj.full_name} <{obj.email}>"


class BillingAdmin(WeblateModelAdmin):
    list_display = (
        "list_projects",
        "list_owners",
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
    search_fields = ("projects__name", "owners__email")
    filter_horizontal = ("projects", "owners")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("projects", "owners")

    @admin.display(description=gettext_lazy("Projects"))
    def list_projects(self, obj):
        if not obj.all_projects:
            return "none projects associated"
        return ",".join(project.name for project in obj.all_projects)

    @admin.display(description=gettext_lazy("Owners"))
    def list_owners(self, obj):
        return ",".join(owner.full_name for owner in obj.owners.all())

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["owners"].label_from_instance = format_user
        return form

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Add owners as admin if there is none
        for project in obj.projects.all():
            group = project.defined_groups.get(name="Administration")
            if not group.user_set.exists():
                group.user_set.add(*obj.owners.all())


class InvoiceAdmin(WeblateModelAdmin):
    list_display = ("billing", "start", "end", "amount", "currency", "ref")
    list_filter = (
        "currency",
        ("billing__projects", RelatedOnlyFieldListFilter),
        ("billing__owners", RelatedOnlyFieldListFilter),
    )
    search_fields = ("billing__projects__name", "ref", "note")
    date_hierarchy = "end"
    ordering = ["billing", "-start"]
