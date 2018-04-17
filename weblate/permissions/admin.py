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

from django.utils.translation import ugettext_lazy as _

from weblate.wladmin.models import WeblateModelAdmin


class GroupACLAdmin(WeblateModelAdmin):
    list_display = ['language', 'project_component', 'group_list']
    filter_horizontal = ('permissions', 'groups')

    def group_list(self, obj):
        groups = obj.groups.values_list('name', flat=True)
        ret = ', '.join(groups[:5])
        if len(groups) > 5:
            ret += ', ...'
        return ret

    def project_component(self, obj):
        if obj.component:
            return obj.component
        return obj.project
    project_component.short_description = _('Project / Component')


class AutoGroupAdmin(WeblateModelAdmin):
    list_display = ('group', 'match')
