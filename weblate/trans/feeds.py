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

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.utils.translation import ugettext as _
from django.shortcuts import get_object_or_404
from django.urls import reverse

from weblate.trans.models import Change
from weblate.lang.models import Language
from weblate.utils.views import (
    get_translation, get_component, get_project
)


class ChangesFeed(Feed):
    """Generic RSS feed for Weblate changes."""
    def get_object(self, request, *args, **kwargs):
        return request.user

    def title(self):
        return _('Recent changes in %s') % settings.SITE_TITLE

    def description(self):
        return _('All recent changes made using Weblate in %s.') % (
            settings.SITE_TITLE
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
    """RSS feed for changes in translation."""

    # Arguments number differs from overridden method
    # pylint: disable=arguments-differ

    def get_object(self, request, project, component, lang):
        return get_translation(request, project, component, lang)

    def title(self, obj):
        return _('Recent changes in %s') % obj

    def description(self, obj):
        return _('All recent changes made using Weblate in %s.') % obj

    def link(self, obj):
        return obj.get_absolute_url()

    def items(self, obj):
        return Change.objects.filter(translation=obj)[:10]


class ComponentChangesFeed(TranslationChangesFeed):
    """RSS feed for changes in component."""

    # Arguments number differs from overridden method
    # pylint: disable=arguments-differ

    def get_object(self, request, project, component):
        return get_component(request, project, component)

    def items(self, obj):
        return Change.objects.filter(component=obj)[:10]


class ProjectChangesFeed(TranslationChangesFeed):
    """RSS feed for changes in project."""

    # Arguments number differs from overridden method
    # pylint: disable=arguments-differ

    def get_object(self, request, project):
        return get_project(request, project)

    def items(self, obj):
        return Change.objects.filter(project=obj)[:10]


class LanguageChangesFeed(TranslationChangesFeed):
    """RSS feed for changes in language."""

    # Arguments number differs from overridden method
    # pylint: disable=arguments-differ

    def get_object(self, request, lang):
        return get_object_or_404(Language, code=lang)

    def items(self, obj):
        return Change.objects.filter(translation__language=obj)[:10]
