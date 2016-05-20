# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.shortcuts import render, get_object_or_404
from django.http import (
    HttpResponse, HttpResponseBadRequest, Http404, JsonResponse,
)
from django.core.exceptions import PermissionDenied
from django.utils.encoding import force_text

from weblate.trans.models import Unit, Check, Change
from weblate.trans.machine import MACHINE_TRANSLATION_SERVICES
from weblate.trans.views.helper import (
    get_project, get_subproject, get_translation
)
from weblate.trans.forms import PriorityForm, CheckFlagsForm
from weblate.trans.validators import EXTRA_FLAGS
from weblate.trans.checks import CHECKS
from weblate.trans.permissions import (
    can_use_mt, can_see_repository_status, can_ignore_check,
)

from six.moves.urllib.parse import urlencode


def translate(request, unit_id):
    '''
    AJAX handler for translating.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)
    if not can_use_mt(request.user, unit.translation):
        raise PermissionDenied()

    service_name = request.GET.get('service', 'INVALID')

    if service_name not in MACHINE_TRANSLATION_SERVICES:
        return HttpResponseBadRequest('Invalid service specified')

    translation_service = MACHINE_TRANSLATION_SERVICES[service_name]

    # Error response
    response = {
        'responseStatus': 500,
        'service': translation_service.name,
        'responseDetails': '',
        'translations': [],
        'lang': unit.translation.language.code,
        'dir': unit.translation.language.direction,
    }

    try:
        response['translations'] = translation_service.translate(
            unit.translation.language.code,
            unit.get_source_plurals()[0],
            unit,
            request.user
        )
        response['responseStatus'] = 200
    except Exception as exc:
        response['responseDetails'] = '%s: %s' % (
            exc.__class__.__name__,
            str(exc)
        )

    return JsonResponse(
        data=response,
    )


def get_unit_changes(request, unit_id):
    '''
    Returns unit's recent changes.
    '''
    unit = get_object_or_404(Unit, pk=int(unit_id))
    unit.check_acl(request)

    return render(
        request,
        'js/changes.html',
        {
            'last_changes': unit.change_set.all()[:10],
            'last_changes_url': urlencode(unit.translation.get_kwargs()),
        }
    )


def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))

    if not can_ignore_check(request.user, obj.project):
        raise PermissionDenied()

    obj.project.check_acl(request)
    # Mark check for ignoring
    obj.set_ignore()
    # response for AJAX
    return HttpResponse('ok')


def git_status_project(request, project):
    obj = get_project(request, project)

    if not can_see_repository_status(request.user, obj):
        raise PermissionDenied()

    statuses = [
        (force_text(component), component.repository.status)
        for component in obj.all_repo_components()
    ]

    return render(
        request,
        'js/git-status.html',
        {
            'object': obj,
            'project': obj,
            'changes': Change.objects.filter(
                subproject__project=obj,
                action__in=Change.ACTIONS_REPOSITORY,
            )[:10],
            'statuses': statuses,
        }
    )


def git_status_subproject(request, project, subproject):
    obj = get_subproject(request, project, subproject)

    if not can_see_repository_status(request.user, obj.project):
        raise PermissionDenied()

    target = obj
    if target.is_repo_link:
        target = target.linked_subproject

    return render(
        request,
        'js/git-status.html',
        {
            'object': obj,
            'project': obj.project,
            'changes': Change.objects.filter(
                action__in=Change.ACTIONS_REPOSITORY,
                subproject=target,
            )[:10],
            'statuses': [(None, obj.repository.status)],
        }
    )


def git_status_translation(request, project, subproject, lang):
    obj = get_translation(request, project, subproject, lang)

    if not can_see_repository_status(request.user, obj.subproject.project):
        raise PermissionDenied()

    target = obj.subproject
    if target.is_repo_link:
        target = target.linked_subproject

    return render(
        request,
        'js/git-status.html',
        {
            'object': obj,
            'project': obj.subproject.project,
            'changes': Change.objects.filter(
                action__in=Change.ACTIONS_REPOSITORY,
                subproject=target,
            )[:10],
            'statuses': [(None, obj.subproject.repository.status)],
        }
    )


def mt_services(request):
    '''
    Generates list of installed machine translation services in JSON.
    '''
    # Machine translation
    machine_services = list(MACHINE_TRANSLATION_SERVICES.keys())

    return JsonResponse(
        data=machine_services,
        safe=False,
    )


def get_detail(request, project, subproject, checksum):
    '''
    Returns source translation detail in all languages.
    '''
    subproject = get_subproject(request, project, subproject)
    units = Unit.objects.filter(
        checksum=checksum,
        translation__subproject=subproject
    )
    try:
        source = units[0].source_info
    except IndexError:
        raise Http404('Non existing unit!')

    check_flags = [
        (CHECKS[x].ignore_string, CHECKS[x].name) for x in CHECKS
    ]
    extra_flags = [(x, EXTRA_FLAGS[x]) for x in EXTRA_FLAGS]

    return render(
        request,
        'js/detail.html',
        {
            'units': units,
            'source': source,
            'project': subproject.project,
            'next': request.GET.get('next', ''),
            'priority_form': PriorityForm(
                initial={'priority': source.priority}
            ),
            'check_flags_form': CheckFlagsForm(
                initial={'flags': source.check_flags}
            ),
            'extra_flags': extra_flags,
            'check_flags': check_flags,
        }
    )
