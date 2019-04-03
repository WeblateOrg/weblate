# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from weblate.wladmin.models import WeblateModelAdmin


class AuditLogAdmin(WeblateModelAdmin):
    list_display = [
        'get_message',
        'user',
        'address',
        'user_agent',
        'timestamp',
    ]
    search_fields = [
        'user__username',
        'user__email',
        'address',
        'activity',
    ]
    date_hierarchy = 'timestamp'


class ProfileAdmin(WeblateModelAdmin):
    list_display = [
        'user', 'full_name', 'language', 'suggested', 'translated'
    ]
    search_fields = [
        'user__username', 'user__email', 'user__full_name'
    ]
    list_filter = ['language']
    filter_horizontal = ('languages', 'secondary_languages', 'subscriptions')


class VerifiedEmailAdmin(WeblateModelAdmin):
    list_display = ('social', 'email')
    search_fields = (
        'email', 'social__user__username', 'social__user__email'
    )
    raw_id_fields = ('social',)
