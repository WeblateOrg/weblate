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

from django.http import Http404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.decorators import permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_POST
from django.contrib import messages

from weblate.trans.views.helper import get_subproject
from weblate.trans.models import Translation, Source
from weblate.trans.forms import PriorityForm, CheckFlagsForm


def get_source(request, project, subproject):
    """
    Returns first translation in subproject
    (this assumes all have same source strings).
    """
    obj = get_subproject(request, project, subproject)
    try:
        return obj, obj.translation_set.all()[0]
    except (Translation.DoesNotExist, IndexError):
        raise Http404('No translation exists in this component.')


def review_source(request, project, subproject):
    """
    Listing of source strings to review.
    """
    obj, source = get_source(request, project, subproject)

    # Grab search type and page number
    rqtype = request.GET.get('type', 'all')
    limit = request.GET.get('limit', 50)
    page = request.GET.get('page', 1)
    checksum = request.GET.get('checksum', '')
    ignored = 'ignored' in request.GET
    expand = False

    # Filter units:
    if checksum:
        sources = source.unit_set.filter(checksum=checksum)
        expand = True
    else:
        sources = source.unit_set.filter_type(rqtype, source, ignored)

    paginator = Paginator(sources, limit)

    try:
        sources = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        sources = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        sources = paginator.page(paginator.num_pages)

    return render(
        request,
        'source-review.html',
        {
            'object': obj,
            'source': source,
            'page_obj': sources,
            'rqtype': rqtype,
            'ignored': ignored,
            'expand': expand,
            'title': _('Review source strings in %s') % obj.__unicode__(),
        }
    )


def show_source(request, project, subproject):
    """
    Show source strings summary and checks.
    """
    obj, source = get_source(request, project, subproject)

    return render(
        request,
        'source.html',
        {
            'object': obj,
            'source': source,
            'title': _('Source strings in %s') % obj.__unicode__(),
        }
    )


@require_POST
@permission_required('edit_priority')
def edit_priority(request, pk):
    """
    Change source string priority.
    """
    source = get_object_or_404(Source, pk=pk)
    form = PriorityForm(request.POST)
    if form.is_valid():
        source.priority = form.cleaned_data['priority']
        source.save()
    else:
        messages.error(request, _('Failed to change a priority!'))
    return redirect(request.POST.get('next', source.get_absolute_url()))


@require_POST
@permission_required('edit_check_flags')
def edit_check_flags(request, pk):
    """
    Change source string check flags.
    """
    source = get_object_or_404(Source, pk=pk)
    form = CheckFlagsForm(request.POST)
    if form.is_valid():
        source.check_flags = form.cleaned_data['flags']
        source.save()
    else:
        messages.error(request, _('Failed to change check flags!'))
    return redirect(request.POST.get('next', source.get_absolute_url()))
