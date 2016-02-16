# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals
from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from weblate.billing.models import Plan, Billing, Invoice


class PlanAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'price', 'limit_strings', 'limit_languages',
        'limit_repositories', 'limit_projects',
        'display_limit_strings', 'display_limit_languages',
        'display_limit_repositories', 'display_limit_projects',
    )


class BillingAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'plan', 'state',
        'list_projects',
        'count_changes_1m', 'count_changes_1q', 'count_changes_1y',
        'count_repositories', 'count_strings', 'count_words',
        'count_languages',
        'in_limits',
    )
    list_filter = ('plan', 'state')
    search_fields = ('user__username', 'projects__name')

    def list_projects(self, obj):
        return ','.join(obj.projects.values_list('name', flat=True))
    list_projects.short_description = _('Projects')


class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'billing', 'start', 'end', 'payment', 'currency', 'ref'
    )
    list_filter = ('currency', 'billing')
    search_fields = (
        'billing__user__username', 'billing__projects__name',
        'ref', 'note',
    )
    date_hierarchy = 'end'


admin.site.register(Plan, PlanAdmin)
admin.site.register(Billing, BillingAdmin)
admin.site.register(Invoice, InvoiceAdmin)
