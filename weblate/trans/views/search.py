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

from __future__ import unicode_literals

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, EmptyPage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import ugettext as _, ungettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.permissions.helpers import can_translate
from weblate.trans.forms import (
    SiteSearchForm, ReplaceForm, ReplaceConfirmForm,
)
from weblate.trans.models import Unit, Change, Project
from weblate.trans.views.helper import (
    get_translation, get_subproject, get_project, import_message,
)
from weblate.trans.util import render
from weblate.utils import messages
from weblate.utils.views import get_page_limit


@login_required
@require_POST
def search_replace(request, project, subproject=None, lang=None):
    context = {}
    if subproject is None:
        obj = get_project(request, project)
        perms = {'project': obj}
        unit_set = Unit.objects.filter(translation__subproject__project=obj)
        context['project'] = obj
    elif lang is None:
        obj = get_subproject(request, project, subproject)
        perms = {'project': obj.project}
        unit_set = Unit.objects.filter(translation__subproject=obj)
        context['subproject'] = obj
        context['project'] = obj.project
    else:
        obj = get_translation(request, project, subproject, lang)
        perms = {'translation': obj}
        unit_set = obj.unit_set
        context['translation'] = obj
        context['subproject'] = obj.subproject
        context['project'] = obj.subproject.project

    if not can_translate(request.user, **perms):
        raise PermissionDenied()

    form = ReplaceForm(request.POST)

    if not form.is_valid():
        messages.error(request, _('Failed to process form!'))
        return redirect(obj)

    search_text = form.cleaned_data['search']
    replacement = form.cleaned_data['replacement']

    matching = unit_set.filter(target__contains=search_text)

    updated = 0
    if matching.exists():
        confirm = ReplaceConfirmForm(matching, request.POST)

        if not confirm.is_valid():
            for unit in matching:
                unit.replacement = unit.target.replace(
                    search_text, replacement
                )
            context.update({
                'matching': matching,
                'search_query': search_text,
                'replacement': replacement,
                'form': form,
                'confirm': ReplaceConfirmForm(matching),
            })
            return render(
                request,
                'replace.html',
                context
            )

        matching = confirm.cleaned_data['units']

        with transaction.atomic():
            for unit in matching.select_for_update():
                if not can_translate(request.user, unit):
                    continue
                unit.translate(
                    request,
                    unit.target.replace(search_text, replacement),
                    unit.state,
                    change_action=Change.ACTION_REPLACE
                )
                updated += 1

    import_message(
        request, updated,
        _('Search and replace completed, no strings were updated.'),
        ungettext(
            'Search and replace completed, %d string was updated.',
            'Search and replace completed, %d strings were updated.',
            updated
        )
    )

    return redirect(obj)


@never_cache
def search(request, project=None, subproject=None, lang=None):
    """Perform site-wide search on units."""
    search_form = SiteSearchForm(request.GET)
    context = {
        'search_form': search_form,
    }
    search_kwargs = {}
    if subproject:
        obj = get_subproject(request, project, subproject)
        context['subproject'] = obj
        context['project'] = obj.project
        search_kwargs = {'subproject': obj}
    elif project:
        obj = get_project(request, project)
        context['project'] = obj
        search_kwargs = {'project': obj}
    else:
        obj = None
    if lang:
        s_language = get_object_or_404(Language, code=lang)
        context['language'] = s_language
        search_kwargs = {'language': s_language}

    if search_form.is_valid():
        # Filter results by ACL
        if subproject:
            units = Unit.objects.filter(translation__subproject=obj)
        elif project:
            units = Unit.objects.filter(translation__subproject__project=obj)
        else:
            projects = Project.objects.get_acl_ids(request.user)
            units = Unit.objects.filter(
                translation__subproject__project_id__in=projects
            )
        units = units.search(
            search_form.cleaned_data,
            **search_kwargs
        )
        if lang:
            units = units.filter(
                translation__language=context['language']
            )

        page, limit = get_page_limit(request, 50)

        paginator = Paginator(units, limit)

        try:
            units = paginator.page(page)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of
            # results.
            units = paginator.page(paginator.num_pages)

        context['page_obj'] = units
        context['title'] = _('Search for %s') % (
            search_form.cleaned_data['q']
        )
        context['query_string'] = search_form.urlencode()
        context['search_query'] = search_form.cleaned_data['q']
    else:
        messages.error(request, _('Invalid search query!'))

    return render(
        request,
        'search.html',
        context
    )
