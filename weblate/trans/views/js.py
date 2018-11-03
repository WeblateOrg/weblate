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

from django.shortcuts import render, get_object_or_404
from django.http import (
    HttpResponse, HttpResponseBadRequest, Http404, JsonResponse,
)
from django.core.exceptions import PermissionDenied
from django.utils.encoding import force_text
from django.utils.http import urlencode

from weblate.checks.models import Check
from weblate.screenshots.forms import ScreenshotForm
from weblate.trans.models import Unit, Change
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.utils.views import (
    get_project, get_component, get_translation
)
from weblate.trans.forms import PriorityForm, CheckFlagsForm, ContextForm
from weblate.trans.validators import EXTRA_FLAGS
from weblate.checks import CHECKS
from weblate.utils.hash import checksum_to_hash
from weblate.trans.util import sort_objects


def translate(request, unit_id, service):
    """AJAX handler for translating."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access(unit.translation.component.project)
    if not request.user.has_perm('machinery.view', unit.translation):
        raise PermissionDenied()

    if service not in MACHINE_TRANSLATION_SERVICES:
        return HttpResponseBadRequest('Invalid service specified')

    translation_service = MACHINE_TRANSLATION_SERVICES[service]

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
        response['responseDetails'] = '{0}: {1}'.format(
            exc.__class__.__name__,
            str(exc)
        )

    return JsonResponse(
        data=response,
    )


def get_unit_changes(request, unit_id):
    """Return unit's recent changes."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access(unit.translation.component.project)

    return render(
        request,
        'js/changes.html',
        {
            'last_changes': unit.change_set.all()[:10],
            'last_changes_url': urlencode(
                unit.translation.get_reverse_url_kwargs()
            ),
        }
    )


def get_unit_translations(request, unit_id):
    """Return unit's other translations."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access(unit.translation.component.project)

    return render(
        request,
        'js/translations.html',
        {
            'units': sort_objects(
                Unit.objects.filter(
                    id_hash=unit.id_hash,
                    translation__component=unit.translation.component,
                ).exclude(
                    pk=unit.pk
                )
            ),
        }
    )


def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    request.user.check_access(obj.project)

    if not request.user.has_perm('unit.check', obj.project):
        raise PermissionDenied()

    # Mark check for ignoring
    obj.set_ignore()
    # response for AJAX
    return HttpResponse('ok')


def git_status_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm('meta:vcs.status', obj):
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
                component__project=obj,
                action__in=Change.ACTIONS_REPOSITORY,
            )[:10],
            'statuses': statuses,
        }
    )


def git_status_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm('meta:vcs.status', obj):
        raise PermissionDenied()

    target = obj
    if target.is_repo_link:
        target = target.linked_component

    return render(
        request,
        'js/git-status.html',
        {
            'object': obj,
            'project': obj.project,
            'changes': Change.objects.filter(
                action__in=Change.ACTIONS_REPOSITORY,
                component=target,
            )[:10],
            'statuses': [(None, obj.repository.status)],
        }
    )


def git_status_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm('meta:vcs.status', obj):
        raise PermissionDenied()

    target = obj.component
    if target.is_repo_link:
        target = target.linked_component

    return render(
        request,
        'js/git-status.html',
        {
            'object': obj,
            'translation': obj,
            'project': obj.component.project,
            'changes': Change.objects.filter(
                action__in=Change.ACTIONS_REPOSITORY,
                component=target,
            )[:10],
            'statuses': [(None, obj.component.repository.status)],
        }
    )


def mt_services(request):
    """Generate list of installed machine translation services in JSON."""
    # Machine translation
    machine_services = list(MACHINE_TRANSLATION_SERVICES.keys())

    return JsonResponse(
        data=machine_services,
        safe=False,
    )


def get_detail(request, project, component, checksum):
    """Return source translation detail in all languages."""
    component = get_component(request, project, component)
    try:
        units = Unit.objects.filter(
            id_hash=checksum_to_hash(checksum),
            translation__component=component
        )
    except ValueError:
        raise Http404('Non existing unit!')
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
            'project': component.project,
            'next': request.GET.get('next', ''),
            'priority_form': PriorityForm(
                initial={'priority': source.priority}
            ),
            'context_form': ContextForm(
                initial={'context': source.context}
            ),

            'check_flags_form': CheckFlagsForm(
                initial={'flags': source.check_flags}
            ),
            'screenshot_form': ScreenshotForm(),
            'extra_flags': extra_flags,
            'check_flags': check_flags,
        }
    )
