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

import csv

from django.views.generic.list import ListView
from django.http import Http404, HttpResponse
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _, activate
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from six.moves.urllib.parse import urlencode

from weblate.trans import messages
from weblate.trans.models.changes import Change
from weblate.trans.views.helper import get_project_translation
from weblate.lang.models import Language
from weblate.trans.permissions import can_download_changes


class ChangesView(ListView):
    '''
    Browser for changes.
    '''
    paginate_by = 20

    def __init__(self, **kwargs):
        super(ChangesView, self).__init__(**kwargs)
        self.project = None
        self.subproject = None
        self.translation = None
        self.language = None
        self.user = None
        self.glossary = False

    def get_context_data(self, **kwargs):
        '''
        Creates context for rendering page.
        '''
        context = super(ChangesView, self).get_context_data(
            **kwargs
        )
        context['title'] = _('Changes')
        context['project'] = self.project

        url = {}

        if self.translation is not None:
            url['lang'] = self.translation.language.code
            url['subproject'] = self.translation.subproject.slug
            url['project'] = self.translation.subproject.project.slug
            context['changes_rss'] = reverse(
                'rss-translation',
                kwargs=url,
            )
        elif self.subproject is not None:
            url['subproject'] = self.subproject.slug
            url['project'] = self.subproject.project.slug
            context['changes_rss'] = reverse(
                'rss-subproject',
                kwargs=url,
            )
        elif self.project is not None:
            url['project'] = self.project.slug
            context['changes_rss'] = reverse(
                'rss-project',
                kwargs=url,
            )

        if self.language is not None:
            url['lang'] = self.language.code
            if 'changes_rss' not in context:
                context['changes_rss'] = reverse(
                    'rss-language',
                    kwargs=url,
                )

        if self.user is not None:
            url['user'] = self.user.username.encode('utf-8')

        if self.glossary:
            url['glossary'] = 1

        if len(url) == 0:
            context['changes_rss'] = reverse('rss')

        context['query_string'] = urlencode(url)

        return context

    def _get_queryset_project(self):
        """
        Filtering by translation/project.
        """
        if 'project' in self.request.GET:
            try:
                self.project, self.subproject, self.translation = \
                    get_project_translation(
                        self.request,
                        self.request.GET.get('project', None),
                        self.request.GET.get('subproject', None),
                        self.request.GET.get('lang', None),
                    )
            except Http404:
                messages.error(
                    self.request,
                    _('Failed to find matching project!')
                )

    def _get_queryset_language(self):
        """
        Filtering by language
        """
        if self.translation is None and 'lang' in self.request.GET:
            try:
                self.language = Language.objects.get(
                    code=self.request.GET['lang']
                )
            except Language.DoesNotExist:
                messages.error(
                    self.request,
                    _('Failed to find matching language!')
                )

    def _get_queryset_user(self):
        """
        Filtering by user
        """
        if 'user' in self.request.GET:
            try:
                self.user = User.objects.get(
                    username=self.request.GET['user']
                )
            except User.DoesNotExist:
                messages.error(
                    self.request,
                    _('Failed to find matching user!')
                )

    def get_queryset(self):
        '''
        Returns list of changes to browse.
        '''
        self._get_queryset_project()

        self._get_queryset_language()

        self._get_queryset_user()

        # Glossary entries
        self.glossary = 'glossary' in self.request.GET

        result = Change.objects.last_changes(self.request.user)

        if self.translation is not None:
            result = result.filter(
                translation=self.translation
            )
        elif self.subproject is not None:
            result = result.filter(
                translation__subproject=self.subproject
            )
        elif self.project is not None:
            result = result.filter(
                Q(translation__subproject__project=self.project) |
                Q(dictionary__project=self.project)
            )

        if self.language is not None:
            result = result.filter(
                Q(translation__language=self.language) |
                Q(dictionary__language=self.language)
            )

        if self.glossary:
            result = result.filter(
                dictionary__isnull=False
            )

        if self.user is not None:
            result = result.filter(
                user=self.user
            )

        return result


class ChangesCSVView(ChangesView):
    """CSV renderer for changes view"""
    paginate_by = None

    def get(self, request, *args, **kwargs):
        object_list = self.get_queryset()

        if not can_download_changes(request.user, self.project):
            raise PermissionDenied()

        # Always output in english
        activate('en')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename=changes.csv'

        writer = csv.writer(response)

        # Add header
        writer.writerow(('timestamp', 'action', 'user', 'url'))

        for change in object_list[:2000].iterator():
            writer.writerow((
                change.timestamp.isoformat(),
                change.get_action_display().encode('utf8'),
                change.user.username.encode('utf8') if change.user else '',
                change.get_absolute_url(),
            ))

        return response
