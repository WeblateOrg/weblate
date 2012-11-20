# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from django.conf import settings
from django.core.urlresolvers import reverse

from weblate.trans.models import Change, Translation, SubProject, Project

class ChangesFeed(Feed):

    def title(self):
        return _('Recent changes in %s') % settings.SITE_TITLE

    def description(self):
        return _('All recent changes made using Weblate in %s.') % settings.SITE_TITLE

    def link(self):
        return reverse('home')

    def items(self, obj):
        return Change.objects.order_by('-timestamp')[:10]

    def item_title(self, item):
        return item.get_action_display()

    def item_description(self, item):
        return str(item)

    def item_author_name(self, item):
        return item.get_user_display()

    def item_pubdate(self, item):
        return item.timestamp


class TranslationChangesFeed(ChangesFeed):

    def get_object(self, request, project, subproject, lang):
        return get_object_or_404(Translation, language__code = lang, subproject__slug = subproject, subproject__project__slug = project, enabled = True)

    def title(self, obj):
        return _('Recent changes in %s') % obj

    def description(self, obj):
        return _('All recent changes made using Weblate in %s.') % obj

    def link(self, obj):
        return obj.get_absolute_url()

    def items(self, obj):
        return Change.objects.filter(translation = obj).order_by('-timestamp')[:10]

class SubProjectChangesFeed(TranslationChangesFeed):

    def get_object(self, request, project, subproject):
        return get_object_or_404(SubProject, slug = subproject, project__slug = project)

    def items(self, obj):
        return Change.objects.filter(translation__subproject = obj).order_by('-timestamp')[:10]

class ProjectChangesFeed(TranslationChangesFeed):

    def get_object(self, request, project):
        return get_object_or_404(Project, slug = project)

    def items(self, obj):
        return Change.objects.filter(translation__subproject__project = obj).order_by('-timestamp')[:10]
