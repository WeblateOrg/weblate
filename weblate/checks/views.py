# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from django.db.models import Count, F
from django.http import Http404
from django.shortcuts import render
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.utils.translation import ugettext as _

from weblate.checks import CHECKS
from weblate.checks.models import Check
from weblate.trans.util import redirect_param
from weblate.utils.views import get_component, get_project


def acl_checks(user):
    """Filter checks by ACL."""
    return Check.objects.filter(
        unit__translation__component__project__in=user.allowed_projects
    )


def encode_optional(params):
    if params:
        return '?{0}'.format(urlencode(params))
    return ''


def show_checks(request):
    """List of failing checks."""
    ignore = ('ignored' in request.GET)
    url_params = {}

    if ignore:
        url_params['ignored'] = 'true'

    allchecks = acl_checks(request.user).filter(
        ignore=ignore,
    )

    if request.GET.get('project'):
        allchecks = allchecks.filter(
            unit__translation__component__project__slug=request.GET['project']
        )
        url_params['project'] = request.GET['project']

    if request.GET.get('language'):
        allchecks = allchecks.filter(
            unit__translation__language__code=request.GET['language']
        )
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
    """Show details about failing check."""
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    ignore = ('ignored' in request.GET)

    url_params = {}

    if ignore:
        url_params['ignored'] = 'true'

    checks = acl_checks(request.user).filter(
        check=name,
        ignore=ignore,
    )

    if request.GET.get('language'):
        checks = checks.filter(
            unit__translation__language__code=request.GET['language']
        )
        url_params['language'] = request.GET['language']

    if request.GET.get('project') and '/' not in request.GET['project']:
        return redirect_param(
            'show_check_project',
            encode_optional(url_params),
            project=request.GET['project'],
            name=name,
        )

    checks = checks.values(
        project__slug=F('unit__translation__component__project__slug')
    ).annotate(
        count=Count('id')
    )

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
    """Show checks failing in a project."""
    prj = get_project(request, project)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    ignore = ('ignored' in request.GET)

    url_params = {}

    allchecks = acl_checks(request.user).filter(
        check=name,
        unit__translation__component__project=prj,
        ignore=ignore,
    )

    if ignore:
        url_params['ignored'] = 'true'

    if request.GET.get('language'):
        allchecks = allchecks.filter(
            unit__translation__language__code=request.GET['language']
        )
        url_params['language'] = request.GET['language']

    units = allchecks.values(
        component__slug=F('unit__translation__component__slug'),
        project__slug=F('unit__translation__component__project__slug'),
    ).annotate(
        count=Count('id')
    )

    return render(
        request,
        'check_project.html',
        {
            'checks': units,
            'title': '{0}/{1}'.format(force_text(prj), check.name),
            'check': check,
            'project': prj,
            'url_params': encode_optional(url_params),
        }
    )


def show_check_component(request, name, project, component):
    """Show checks failing in a component."""
    subprj = get_component(request, project, component)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404('No check matches the given query.')

    ignore = ('ignored' in request.GET)
    url_params = {}

    allchecks = acl_checks(request.user).filter(
        check=name,
        unit__translation__component=subprj,
        ignore=ignore,
    )

    if ignore:
        url_params['ignored'] = 'true'

    # Source checks are for single language only, redirect directly there
    if check.source:
        return redirect_param(
            'translate',
            encode_optional({
                'q': '{}{}'.format('ignored_' if ignore else '', check.url_id)
            }),
            project=subprj.project.slug,
            component=subprj.slug,
            lang=subprj.project.source_language.code,
        )

    # When filtering language, redirect directly to it
    if request.GET.get('language') and '/' not in request.GET['language']:
        return redirect_param(
            'translate',
            encode_optional({
                'q': '{}{}'.format('ignored_' if ignore else '', check.url_id)
            }),
            project=subprj.project.slug,
            component=subprj.slug,
            lang=request.GET['language'],
        )

    units = allchecks.values(
        translation__language__code=F('unit__translation__language__code'),
    ).annotate(count=Count('id'))

    return render(
        request,
        'check_component.html',
        {
            'checks': units,
            'ignored': ignore,
            'title': '{0}/{1}'.format(force_text(subprj), check.name),
            'check': check,
            'component': subprj,
            'url_params': encode_optional(url_params),
        }
    )
