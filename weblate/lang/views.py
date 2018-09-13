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

from django.shortcuts import render, redirect
from django.http import Http404
from django.utils.translation import ugettext as _
from django.utils.http import urlencode

from weblate.lang.models import Language
from weblate.trans.forms import SiteSearchForm
from weblate.trans.models import Change
from weblate.trans.util import sort_objects
from weblate.utils.views import get_project
from weblate.utils.stats import prefetch_stats
from weblate.utils.views import get_paginator


def show_languages(request):
    return render(
        request,
        'languages.html',
        {
            'allow_index': True,
            'languages': prefetch_stats(
                sort_objects(
                    Language.objects.have_translation()
                )
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
    projects = request.user.allowed_projects
    dicts = projects.filter(
        dictionary__language=obj
    ).distinct()
    projects = projects.filter(
        component__translation__language=obj
    ).distinct()

    for project in projects:
        project.language_stats = project.stats.get_single_language_stats(obj)

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
        component__project=pobj
    )[:10]

    # Paginate translations.
    translation_list = obj.translation_set.prefetch().filter(
        component__project=pobj
    ).order_by(
        'component__project__slug', 'component__slug'
    )
    translations = get_paginator(request, translation_list)

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
