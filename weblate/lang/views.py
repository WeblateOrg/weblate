# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from django.shortcuts import render, redirect
from django.http import Http404
from django.utils.translation import ugettext as _
from django.utils.http import urlencode

from weblate.lang.models import Language
from weblate.trans.forms import SiteSearchForm
from weblate.trans.models import Project, Change
from weblate.trans.stats import get_per_language_stats
from weblate.trans.util import sort_objects, translation_percent
from weblate.trans.views.helper import get_project


def show_languages(request):
    return render(
        request,
        'languages.html',
        {
            'allow_index': True,
            'languages': sort_objects(
                Language.objects.have_translation()
            ),
            'title': _('Languages'),
        }
    )


def show_language(request, lang):
    try:
        obj = Language.objects.get(code=lang)
    except Language.DoesNotExist:
        obj = Language.objects.fuzzy_get(lang)
        if isinstance(obj, Language):
            return redirect(obj)
        raise Http404('No Language matches the given query.')

    last_changes = Change.objects.last_changes(request.user).filter(
        translation__language=obj
    )[:10]
    projects = Project.objects.all_acl(request.user)
    dicts = projects.filter(
        dictionary__language=obj
    ).distinct()
    projects = projects.filter(
        subproject__translation__language=obj
    ).distinct()

    for project in projects:
        stats = get_per_language_stats(project, obj)
        project.language_stats = (
            translation_percent(stats[0][1], stats[0][2]),
            translation_percent(stats[0][3], stats[0][4])
        )

    return render(
        request,
        'language.html',
        {
            'allow_index': True,
            'object': obj,
            'last_changes': last_changes,
            'last_changes_url': urlencode({'lang': obj.code}),
            'dicts': dicts,
            'projects': projects,
        }
    )


def show_project(request, lang, project):
    try:
        obj = Language.objects.get(code=lang)
    except Language.DoesNotExist:
        obj = Language.objects.fuzzy_get(lang)
        if isinstance(obj, Language):
            return redirect(obj)
        raise Http404('No Language matches the given query.')

    pobj = get_project(request, project)

    last_changes = Change.objects.last_changes(request.user).filter(
        translation__language=obj,
        subproject__project=pobj
    )[:10]
    translations = obj.translation_set.enabled().filter(
        subproject__project=pobj
    ).order_by(
        'subproject__project__slug', 'subproject__slug'
    )

    return render(
        request,
        'language-project.html',
        {
            'allow_index': True,
            'language': obj,
            'project': pobj,
            'last_changes': last_changes,
            'last_changes_url': urlencode(
                {'lang': obj.code, 'project': pobj.slug}
            ),
            'translations': translations,
            'title': '{0} - {1}'.format(pobj, obj),
            'show_only_component': True,
            'search_form': SiteSearchForm(),
        }
    )
