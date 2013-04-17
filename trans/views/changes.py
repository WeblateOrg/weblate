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
from django.http import Http404
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _
from trans.models.changes import Change
from trans.views.helper import get_project_translation
from lang.models import Language


class ChangesView(ListView):
    '''
    Browser for changes.
    '''
    paginate_by = 20

    def get_queryset(self):
        '''
        Returns list of changes to browse.
        '''
        project = None
        subproject = None
        translation = None
        language = None
        user = None

        # Filtering by translation/project
        if 'project' in self.request.GET:
            try:
                project, subproject, translation = get_project_translation(
                    self.request,
                    self.request.GET.get('project', None),
                    self.request.GET.get('subproject', None),
                    self.request.GET.get('lang', None),
                )
            except Http404:
                messages.error(self.request, _('Invalid search string!'))

        # Filtering by language
        if translation is None and 'lang' in self.request.GET:
            try:
                language = Language.objects.get(
                    code=self.request.GET['lang']
                )
            except Language.DoesNotExist:
                messages.error(self.request, _('Invalid search string!'))

        # Filtering by user
        if 'user' in self.request.GET:
            try:
                user = User.objects.get(
                    username=self.request.GET['user']
                )
            except User.DoesNotExist:
                messages.error(self.request, _('Invalid search string!'))

        result = Change.objects.all()

        if translation is not None:
            result = result.filter(translation=translation)
        elif subproject is not None:
            result = result.filter(translation__subproject=subproject)
        elif project is not None:
            result = result.filter(translation__subproject__project=project)

        if language is not None:
            result = result.filter(translation__language=language)

        if user is not None:
            result = result.filter(user=user)

        return result
