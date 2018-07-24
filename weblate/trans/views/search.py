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
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.accounts.ratelimit import check_rate_limit
from weblate.lang.models import Language
from weblate.trans.forms import (
    SiteSearchForm, ReplaceForm, ReplaceConfirmForm, MassStateForm,
)
from weblate.trans.models import Unit, Change
from weblate.trans.views.helper import (
    get_translation, get_component, get_project, import_message,
)
from weblate.trans.util import render
from weblate.trans.views.helper import show_form_errors
from weblate.utils import messages
from weblate.utils.state import STATE_EMPTY
from weblate.utils.views import get_page_limit


def parse_url(request, project, component=None, lang=None):
    context = {}
    if component is None:
        obj = get_project(request, project)
        unit_set = Unit.objects.filter(translation__component__project=obj)
        context['project'] = obj
    elif lang is None:
        obj = get_component(request, project, component)
        unit_set = Unit.objects.filter(translation__component=obj)
        context['component'] = obj
        context['project'] = obj.project
    else:
        obj = get_translation(request, project, component, lang)
        unit_set = obj.unit_set
        context['translation'] = obj
        context['component'] = obj.component
        context['project'] = obj.component.project

    if not request.user.has_perm('unit.edit', obj):
        raise PermissionDenied()

    return obj, unit_set, context


@login_required
@require_POST
def search_replace(request, project, component=None, lang=None):
    obj, unit_set, context = parse_url(request, project, component, lang)

    form = ReplaceForm(request.POST)

    if not form.is_valid():
        messages.error(request, _('Failed to process form!'))
        show_form_errors(request, form)
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

        obj.commit_pending(request)

        with transaction.atomic():
            for unit in matching.select_for_update():
                if not request.user.has_perm('unit.edit', unit):
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
def search(request, project=None, component=None, lang=None):
    """Perform site-wide search on units."""
    if not check_rate_limit('search', request):
        search_form = SiteSearchForm()
    else:
        search_form = SiteSearchForm(request.GET)
    context = {
        'search_form': search_form,
    }
    search_kwargs = {}
    if component:
        obj = get_component(request, project, component)
        context['component'] = obj
        context['project'] = obj.project
        context['back_url'] = obj.get_absolute_url()
        search_kwargs = {'component': obj}
    elif project:
        obj = get_project(request, project)
        context['project'] = obj
        context['back_url'] = obj.get_absolute_url()
        search_kwargs = {'project': obj}
    else:
        obj = None
        context['back_url'] = None
    if lang:
        s_language = get_object_or_404(Language, code=lang)
        context['language'] = s_language
        search_kwargs = {'language': s_language}
        if obj:
            if component:
                context['back_url'] = obj.translation_set.get(
                    language=s_language
                ).get_absolute_url()
            else:
                context['back_url'] = reverse(
                    'project-language',
                    kwargs={
                        'project': project,
                        'lang': lang,
                    }
                )
        else:
            context['back_url'] = s_language.get_absolute_url()

    if search_form.is_valid():
        # Filter results by ACL
        if component:
            units = Unit.objects.filter(translation__component=obj)
        elif project:
            units = Unit.objects.filter(translation__component__project=obj)
        else:
            allowed_projects = request.user.allowed_projects
            units = Unit.objects.filter(
                translation__component__project__in=allowed_projects
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


@login_required
@require_POST
@never_cache
def state_change(request, project, component=None, lang=None):
    obj, unit_set, context = parse_url(request, project, component, lang)

    if not request.user.has_perm('translation.auto', obj):
        raise PermissionDenied()

    form = MassStateForm(request.user, obj, request.POST)

    if not form.is_valid():
        messages.error(request, _('Failed to process form!'))
        show_form_errors(request, form)
        return redirect(obj)

    matching = unit_set.filter_type(
        form.cleaned_data['type'],
        context['project'],
        context['translation'].language if 'translation' in context else None,
    ).exclude(
        state=STATE_EMPTY
    )

    obj.commit_pending(request)

    updated = 0
    with transaction.atomic():
        for unit in matching.select_for_update():
            if not request.user.has_perm('unit.edit', unit):
                continue
            unit.translate(
                request,
                unit.target,
                int(form.cleaned_data['state']),
                change_action=Change.ACTION_MASS_STATE,
            )
            updated += 1

    import_message(
        request, updated,
        _('Mass state change completed, no strings were updated.'),
        ungettext(
            'Mass state change completed, %d string was updated.',
            'Mass state change completed, %d strings were updated.',
            updated
        )
    )

    return redirect(obj)
