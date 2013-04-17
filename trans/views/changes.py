# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.views.generic.list import ListView
from trans.models.changes import Change
from trans.views.helper import get_project_translation

class ChangesView(ListView):
    '''
    Browser for changes.
    '''
    paginate_by = 20

    def get_queryset(self):
        '''
        Returns list of changes to browse.
        '''
        project, subproject, translation = get_project_translation(
            self.request,
            self.request.GET.get('project', None),
            self.request.GET.get('subproject', None),
            self.request.GET.get('lang', None),
        )

        result = Change.objects.all()

        if translation is not None:
            result = result.filter(translation=translation)
        elif subproject is not None:
            result = result.filter(translation__subproject=subproject)
        elif project is not None:
            result = result.filter(translation__subproject__project=project)

        return result
