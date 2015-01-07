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

import urllib

from django.shortcuts import render
from django.utils.translation import ugettext as _
from django.http import Http404
from django.db.models import Count

from weblate.trans.models import Unit, Check
from weblate.trans.checks import CHECKS
from weblate.trans.views.helper import get_project, get_subproject
from weblate.trans.util import redirect_param


def encode_optional(params):
    if params:
        return '?{0}'.format(urllib.urlencode(params))
    else:
        return ''


def show_checks(request):
    '''
    List of failing checks.
    '''
    ignore = ('ignored' in request.GET)
    url_params = {}

    if ignore:
        url_params['ignored'] = 'true'

    allchecks = Check.objects.filter(
        ignore=ignore,
    )

    if 'project' in request.GET:
        allchecks = allchecks.filter(project__slug=request.GET['project'])
        url_params['project'] = request.GET['project']

    if 'language' in request.GET:
        allchecks = allchecks.filter(language__code=request.GET['language'])
        url_params['language'] = request.GET['language']

    allchecks = allchecks.values('check').annotate(count=Count('id'))

    return render(
        request,
        'checks.html',
        {
            'checks': allchecks,
            'title': _('Failing checks'),
            'url_params': encode_optional(url_params),
        }
    )


def show_check(request, name):
    '''
    Details about failing check.
    '''
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    ignore = ('ignored' in request.GET)

    url_params = {}

    if ignore:
        url_params['ignored'] = 'true'

    checks = Check.objects.filter(
        check=name,
        ignore=ignore,
    )

    if 'language' in request.GET:
        checks = checks.filter(language__code=request.GET['language'])
        url_params['language'] = request.GET['language']

    if 'project' in request.GET:
        return redirect_param(
            'show_check_project',
            encode_optional(url_params),
            project=request.GET['project'],
            name=name,
        )

    checks = checks.values('project__slug').annotate(count=Count('id'))

    return render(
        request,
        'check.html',
        {
            'checks': checks,
            'title': check.name,
            'check': check,
            'url_params': encode_optional(url_params),
        }
    )


def show_check_project(request, name, project):
    '''
    Show checks failing in a project.
    '''
    prj = get_project(request, project)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    ignore = ('ignored' in request.GET)

    url_params = {}

    allchecks = Check.objects.filter(
        check=name,
        project=prj,
        ignore=ignore,
    )

    if ignore:
        url_params['ignored'] = 'true'

    if 'language' in request.GET:
        allchecks = allchecks.filter(language__code=request.GET['language'])
        url_params['language'] = request.GET['language']

    units = Unit.objects.none()
    if check.target:
        langs = allchecks.values_list('language', flat=True).distinct()
        for lang in langs:
            checks = allchecks.filter(
                language=lang,
            ).values_list('contentsum', flat=True)
            res = Unit.objects.filter(
                contentsum__in=checks,
                translation__language=lang,
                translation__subproject__project=prj,
                translated=True
            ).values(
                'translation__subproject__slug',
                'translation__subproject__project__slug'
            ).annotate(count=Count('id'))
            units |= res
    if check.source:
        checks = allchecks.filter(
            language=None,
        ).values_list(
            'contentsum', flat=True
        )
        for subproject in prj.subproject_set.all():
            try:
                lang = subproject.translation_set.all()[0].language
            except IndexError:
                continue
            res = Unit.objects.filter(
                contentsum__in=checks,
                translation__language=lang,
                translation__subproject=subproject
            ).values(
                'translation__subproject__slug',
                'translation__subproject__project__slug'
            ).annotate(count=Count('id'))
            units |= res

    counts = {}
    for unit in units:
        key = '{0}/{1}'.format(
            unit['translation__subproject__project__slug'],
            unit['translation__subproject__slug']
        )
        if key in counts:
            counts[key] += unit['count']
        else:
            counts[key] = unit['count']

    units = [
        {
            'translation__subproject__slug': item.split('/')[1],
            'translation__subproject__project__slug': item.split('/')[0],
            'count': counts[item]
        } for item in counts
    ]

    return render(
        request,
        'check_project.html',
        {
            'checks': units,
            'title': '%s/%s' % (prj.__unicode__(), check.name),
            'check': check,
            'project': prj,
            'url_params': encode_optional(url_params),
        }
    )


def show_check_subproject(request, name, project, subproject):
    '''
    Show checks failing in a subproject.
    '''
    subprj = get_subproject(request, project, subproject)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    ignore = ('ignored' in request.GET)
    url_params = {}

    allchecks = Check.objects.filter(
        check=name,
        project=subprj.project,
        ignore=ignore,
    )

    if ignore:
        url_params['ignored'] = 'true'

    if check.source:
        url_params['type'] = check.check_id
        return redirect_param(
            'review_source',
            encode_optional(url_params),
            project=subprj.project.slug,
            subproject=subprj.slug,
        )

    if 'language' in request.GET:
        return redirect_param(
            'translate',
            encode_optional(url_params),
            project=subprj.project.slug,
            subproject=subprj.slug,
            lang=request.GET['language'],
        )

    units = Unit.objects.none()

    if check.target:
        langs = allchecks.values_list(
            'language', flat=True
        ).distinct()
        for lang in langs:
            checks = allchecks.filter(
                language=lang,
            ).values_list('contentsum', flat=True)
            res = Unit.objects.filter(
                translation__subproject=subprj,
                contentsum__in=checks,
                translation__language=lang,
                translated=True
            ).values(
                'translation__language__code'
            ).annotate(count=Count('id'))
            units |= res

    counts = {}
    for unit in units:
        key = unit['translation__language__code']
        if key in counts:
            counts[key] += unit['count']
        else:
            counts[key] = unit['count']

    units = [
        {
            'translation__language__code': item,
            'count': counts[item]
        } for item in counts
    ]

    return render(
        request,
        'check_subproject.html',
        {
            'checks': units,
            'title': '%s/%s' % (subprj.__unicode__(), check.name),
            'check': check,
            'subproject': subprj,
            'url_params': encode_optional(url_params),
        }
    )
