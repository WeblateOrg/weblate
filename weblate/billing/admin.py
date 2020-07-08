#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.utils.translation import gettext_lazy as _

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
    return "{}: {} <{}>".format(obj.username, obj.full_name, obj.email)


class BillingAdmin(WeblateModelAdmin):
    list_display = (
        "list_projects",
        "list_owners",
        "plan",
        "state",
        "removal",
        "expiry",
        "count_changes_1m",
        "count_changes_1q",
        "count_changes_1y",
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
    search_fields = ("projects__name",)
    filter_horizontal = ("projects", "owners")

    def list_projects(self, obj):
        return ",".join(obj.projects.values_list("name", flat=True))

    list_projects.short_description = _("Projects")

    def list_owners(self, obj):
        return ",".join(obj.owners.values_list("full_name", flat=True))

    list_owners.short_description = _("Owners")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["owners"].label_from_instance = format_user
        return form

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        # Add owners as admin if there is none
        for project in obj.projects.all():
            group = project.get_group("@Administration")
            if not group.user_set.exists():
                group.user_set.add(*obj.owners.all())


class InvoiceAdmin(WeblateModelAdmin):
    list_display = ("billing", "start", "end", "amount", "currency", "ref")
    list_filter = ("currency", "billing")
    search_fields = ("billing__projects__name", "ref", "note")
    date_hierarchy = "end"
    ordering = ["billing", "-start"]
