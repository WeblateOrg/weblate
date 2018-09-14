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

from django.http import Http404
from django.http.response import HttpResponseServerError
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.http import urlencode
from django.utils.translation import ugettext as _
from django.utils.encoding import force_text
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.utils import messages
from weblate.utils.views import get_component
from weblate.trans.models import Translation, Source, Unit
from weblate.trans.forms import (
    PriorityForm, CheckFlagsForm, MatrixLanguageForm, ContextForm,
)
from weblate.trans.util import render, redirect_next
from weblate.utils.hash import checksum_to_hash
from weblate.utils.views import get_paginator


def get_source(request, project, component):
    """
    Returns first translation in component
    (this assumes all have same source strings).
    """
    obj = get_component(request, project, component)
    try:
        return obj, obj.translation_set.all()[0]
    except (Translation.DoesNotExist, IndexError):
        raise Http404('No translation exists in this component.')


def review_source(request, project, component):
    """Listing of source strings to review."""
    obj, source = get_source(request, project, component)

    # Grab search type and page number
    rqtype = request.GET.get('type', 'all')
    try:
        id_hash = checksum_to_hash(request.GET.get('checksum', ''))
    except ValueError:
        id_hash = None
    ignored = 'ignored' in request.GET
    expand = False
    query_string = {'type': rqtype}
    if ignored:
        query_string['ignored'] = 'true'

    # Filter units:
    if id_hash:
        sources = source.unit_set.filter(id_hash=id_hash)
        expand = True
    else:
        sources = source.unit_set.filter_type(
            rqtype,
            source.component.project,
            source.language,
            ignored
        )

    sources = get_paginator(request, sources)

    return render(
        request,
        'source-review.html',
        {
            'object': obj,
            'project': obj.project,
            'source': source,
            'page_obj': sources,
            'query_string': urlencode(query_string),
            'ignored': ignored,
            'expand': expand,
            'title': _('Review source strings in %s') % force_text(obj),
        }
    )


def show_source(request, project, component):
    """Show source strings summary and checks."""
    obj, source = get_source(request, project, component)
    source.stats.ensure_all()

    return render(
        request,
        'source.html',
        {
            'object': obj,
            'project': obj.project,
            'source': source,
            'title': _('Source strings in %s') % force_text(obj),
        }
    )


@require_POST
@login_required
def edit_priority(request, pk):
    """Change source string priority."""
    source = get_object_or_404(Source, pk=pk)

    if not request.user.has_perm('source.edit', source.component):
        raise PermissionDenied()

    form = PriorityForm(request.POST)
    if form.is_valid():
        source.priority = form.cleaned_data['priority']
        source.save()
    else:
        messages.error(request, _('Failed to change a priority!'))
    return redirect_next(request.POST.get('next'), source.get_absolute_url())


@require_POST
@login_required
def edit_context(request, pk):
    """Change source string context."""
    source = get_object_or_404(Source, pk=pk)

    if not request.user.has_perm('source.edit', source.component):
        raise PermissionDenied()

    form = ContextForm(request.POST)
    if form.is_valid():
        source.context = form.cleaned_data['context']
        source.save()
    else:
        messages.error(request, _('Failed to change a context!'))
    return redirect_next(request.POST.get('next'), source.get_absolute_url())


@require_POST
@login_required
def edit_check_flags(request, pk):
    """Change source string check flags."""
    source = get_object_or_404(Source, pk=pk)

    if not request.user.has_perm('source.edit', source.component):
        raise PermissionDenied()

    form = CheckFlagsForm(request.POST)
    if form.is_valid():
        source.check_flags = form.cleaned_data['flags']
        source.save()
    else:
        messages.error(request, _('Failed to change check flags!'))
    return redirect_next(request.POST.get('next'), source.get_absolute_url())


@login_required
def matrix(request, project, component):
    """Matrix view of all strings"""
    obj = get_component(request, project, component)

    show = False
    languages = None
    language_codes = None

    if 'lang' in request.GET:
        form = MatrixLanguageForm(obj, request.GET)
        show = form.is_valid()
    else:
        form = MatrixLanguageForm(obj)

    if show:
        languages = Language.objects.filter(
            code__in=form.cleaned_data['lang']
        )
        language_codes = ','.join(languages.values_list('code', flat=True))

    return render(
        request,
        'matrix.html',
        {
            'object': obj,
            'project': obj.project,
            'languages': languages,
            'language_codes': language_codes,
            'languages_form': form,
        }
    )


@login_required
def matrix_load(request, project, component):
    """Backend for matrix view of all strings"""
    obj = get_component(request, project, component)

    try:
        offset = int(request.GET.get('offset', ''))
    except ValueError:
        return HttpResponseServerError('Missing offset')
    language_codes = request.GET.get('lang')
    if not language_codes or offset is None:
        return HttpResponseServerError('Missing lang')

    # Can not use filter to keep ordering
    translations = [
        get_object_or_404(obj.translation_set, language__code=lang)
        for lang in language_codes.split(',')
    ]

    data = []

    for unit in translations[0].unit_set.all()[offset:offset + 20]:
        units = []
        for translation in translations:
            try:
                units.append(translation.unit_set.get(id_hash=unit.id_hash))
            except Unit.DoesNotExist:
                units.append(None)

        data.append((unit, units))

    return render(
        request,
        'matrix-table.html',
        {
            'object': obj,
            'data': data,
            'last': translations[0].unit_set.count() <= offset + 20
        }
    )
