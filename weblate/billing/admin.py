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

from django.utils.translation import ugettext_lazy as _

from weblate.wladmin.models import WeblateModelAdmin


class PlanAdmin(WeblateModelAdmin):
    list_display = (
        'name', 'price', 'limit_strings', 'limit_languages',
        'limit_repositories', 'limit_projects',
        'display_limit_strings', 'display_limit_languages',
        'display_limit_repositories', 'display_limit_projects',
    )


class BillingAdmin(WeblateModelAdmin):
    list_display = (
        'list_projects',
        'plan', 'state',
        'count_changes_1m', 'count_changes_1q', 'count_changes_1y',
        'unit_count',
        'display_projects', 'display_repositories', 'display_strings',
        'display_words', 'display_languages',
        'in_limits', 'in_display_limits', 'last_invoice'
    )
    list_filter = ('plan', 'state')
    search_fields = ('projects__name',)

    def list_projects(self, obj):
        return ','.join(obj.projects.values_list('name', flat=True))
    list_projects.short_description = _('Projects')


class InvoiceAdmin(WeblateModelAdmin):
    list_display = (
        'billing', 'start', 'end', 'payment', 'currency', 'ref'
    )
    list_filter = ('currency', 'billing')
    search_fields = (
        'billing__projects__name', 'ref', 'note',
    )
    date_hierarchy = 'end'
