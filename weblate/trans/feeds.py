# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

from django.contrib.syndication.views import Feed
from django.utils.translation import ugettext as _
from django.shortcuts import get_object_or_404
from weblate import appsettings
from django.core.urlresolvers import reverse

from weblate.trans.models import Change
from weblate.lang.models import Language
from weblate.trans.views.helper import (
    get_translation, get_subproject, get_project
)


class ChangesFeed(Feed):
    '''
    Generic RSS feed for Weblate changes.
    '''
    def get_object(self, request):
        return request.user

    def title(self):
        return _('Recent changes in %s') % appsettings.SITE_TITLE

    def description(self):
        return _('All recent changes made using Weblate in %s.') % (
            appsettings.SITE_TITLE
        )

    def link(self):
        return reverse('home')

    def items(self, obj):
        return Change.objects.last_changes(obj)[:10]

    def item_title(self, item):
        return item.get_action_display()

    def item_description(self, item):
        return str(item)

    def item_author_name(self, item):
        return item.get_user_display(False)

    def item_pubdate(self, item):
        return item.timestamp


class TranslationChangesFeed(ChangesFeed):
    '''
    RSS feed for changes in translation.
    '''

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_object(self, request, project, subproject, lang):
        return get_translation(request, project, subproject, lang)

    def title(self, obj):
        return _('Recent changes in %s') % obj

    def description(self, obj):
        return _('All recent changes made using Weblate in %s.') % obj

    def link(self, obj):
        return obj.get_absolute_url()

    def items(self, obj):
        return Change.objects.filter(
            translation=obj
        )[:10]


class SubProjectChangesFeed(TranslationChangesFeed):
    '''
    RSS feed for changes in subproject.
    '''

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_object(self, request, project, subproject):
        return get_subproject(request, project, subproject)

    def items(self, obj):
        return Change.objects.filter(
            translation__subproject=obj
        )[:10]


class ProjectChangesFeed(TranslationChangesFeed):
    '''
    RSS feed for changes in project.
    '''

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_object(self, request, project):
        return get_project(request, project)

    def items(self, obj):
        return Change.objects.filter(
            translation__subproject__project=obj
        )[:10]


class LanguageChangesFeed(TranslationChangesFeed):
    '''
    RSS feed for changes in language.
    '''

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_object(self, request, lang):
        return get_object_or_404(Language, code=lang)

    def items(self, obj):
        return Change.objects.filter(
            translation__language=obj
        )[:10]
