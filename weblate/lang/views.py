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

from django.shortcuts import render, get_object_or_404
from django.utils.translation import ugettext as _
from django.core.urlresolvers import reverse
from weblate.lang.models import Language
from weblate.trans.models import Project, Dictionary, Change
from urllib import urlencode


def show_languages(request):
    return render(
        request,
        'languages.html',
        {
            'languages': Language.objects.have_translation(),
            'title': _('Languages'),
        }
    )


def show_language(request, lang):
    obj = get_object_or_404(Language, code=lang)
    last_changes = Change.objects.last_changes(request.user).filter(
        translation__language=obj
    )[:10]
    dicts = Dictionary.objects.filter(
        language=obj
    ).values_list('project', flat=True).distinct()
    projects = Project.objects.all_acl(request.user)
    translations = obj.translation_set.enabled().filter(
        subproject__project__in=projects
    ).order_by(
        'subproject__project__slug', 'subproject__slug'
    )

    return render(
        request,
        'language.html',
        {
            'object': obj,
            'last_changes': last_changes,
            'last_changes_rss': reverse(
                'rss-language', kwargs={'lang': obj.code}
            ),
            'last_changes_url': urlencode({'lang': obj.code}),
            'dicts': projects.filter(id__in=dicts),
            'translations': translations,
        }
    )
