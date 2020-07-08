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

from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.encoding import force_str
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.machinery.base import MachineTranslationError
from weblate.trans.models import Change, Unit
from weblate.trans.util import sort_unicode
from weblate.utils.celery import get_task_progress, is_task_ready
from weblate.utils.errors import report_error
from weblate.utils.views import get_component, get_project, get_translation


def handle_machinery(request, service, unit, search=None):
    request.user.check_access_component(unit.translation.component)
    if not request.user.has_perm("machinery.view", unit.translation):
        raise PermissionDenied()

    # Error response
    response = {
        "responseStatus": 500,
        "service": service,
        "responseDetails": "",
        "translations": [],
        "lang": unit.translation.language.code,
        "dir": unit.translation.language.direction,
    }

    try:
        translation_service = MACHINE_TRANSLATION_SERVICES[service]
        response["service"] = translation_service.name
    except KeyError:
        response["responseDetails"] = _("Service is currently not available.")
    else:
        try:
            response["translations"] = translation_service.translate(
                unit, request.user, search=search
            )
            response["responseStatus"] = 200
        except MachineTranslationError as exc:
            response["responseDetails"] = str(exc)
        except Exception as error:
            report_error()
            response["responseDetails"] = "{0}: {1}".format(
                error.__class__.__name__, str(error)
            )

    return JsonResponse(data=response)


@require_POST
def translate(request, unit_id, service):
    """AJAX handler for translating."""
    if service not in MACHINE_TRANSLATION_SERVICES:
        raise Http404("Invalid service specified")

    unit = get_object_or_404(Unit, pk=int(unit_id))
    return handle_machinery(request, service, unit)


@require_POST
def memory(request, unit_id):
    """AJAX handler for translation memory."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    query = request.POST.get("q")
    if not query:
        return HttpResponseBadRequest("Missing search string")

    return handle_machinery(request, "weblate-translation-memory", unit, search=query)


def get_unit_translations(request, unit_id):
    """Return unit's other translations."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access_component(unit.translation.component)

    return render(
        request,
        "js/translations.html",
        {
            "units": sort_unicode(
                Unit.objects.filter(
                    id_hash=unit.id_hash,
                    translation__component=unit.translation.component,
                )
                .exclude(pk=unit.pk)
                .prefetch(),
                lambda unit: str(unit.translation.language),
            )
        },
    )


@require_POST
def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    project = obj.unit.translation.component.project
    request.user.check_access(project)

    if not request.user.has_perm("unit.check", project) or obj.is_enforced():
        raise PermissionDenied()

    # Mark check for ignoring
    obj.set_dismiss("revert" not in request.GET)
    # response for AJAX
    return HttpResponse("ok")


@require_POST
def ignore_check_source(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    unit = obj.unit.source_info
    project = unit.translation.component.project
    request.user.check_access(project)

    if (
        not request.user.has_perm("unit.check", project)
        or obj.is_enforced()
        or not request.user.has_perm("source.edit", unit.translation.component)
    ):
        raise PermissionDenied()

    # Mark check for ignoring
    ignore = obj.check_obj.ignore_string
    flags = Flags(unit.extra_flags)
    if ignore not in flags:
        flags.merge(ignore)
        unit.extra_flags = flags.format()
        unit.save()

    # response for AJAX
    return HttpResponse("ok")


def git_status_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("meta:vcs.status", obj):
        raise PermissionDenied()

    statuses = [
        (force_str(component), component.repository.status)
        for component in obj.all_repo_components()
    ]

    return render(
        request,
        "js/git-status.html",
        {
            "object": obj,
            "project": obj,
            "changes": Change.objects.filter(
                project=obj, action__in=Change.ACTIONS_REPOSITORY
            ).order()[:10],
            "statuses": statuses,
            "component": None,
        },
    )


def git_status_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("meta:vcs.status", obj):
        raise PermissionDenied()

    target = obj
    if target.is_repo_link:
        target = target.linked_component

    return render(
        request,
        "js/git-status.html",
        {
            "object": obj,
            "project": obj.project,
            "changes": Change.objects.filter(
                action__in=Change.ACTIONS_REPOSITORY, component=target
            ).order()[:10],
            "statuses": [(None, obj.repository.status)],
            "component": obj,
        },
    )


def git_status_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("meta:vcs.status", obj):
        raise PermissionDenied()

    target = obj.component
    if target.is_repo_link:
        target = target.linked_component

    return render(
        request,
        "js/git-status.html",
        {
            "object": obj,
            "translation": obj,
            "project": obj.component.project,
            "changes": Change.objects.filter(
                action__in=Change.ACTIONS_REPOSITORY, component=target
            ).order()[:10],
            "statuses": [(None, obj.component.repository.status)],
            "component": obj.component,
        },
    )


@login_required
def task_progress(request, task_id):
    task = AsyncResult(task_id)
    result = task.result
    return JsonResponse(
        {
            "completed": is_task_ready(task),
            "progress": get_task_progress(task),
            "result": str(result) if isinstance(result, Exception) else result,
        }
    )


@cache_control(max_age=3600)
def matomo(request):
    return render(
        request, "js/matomo.js", content_type='text/javascript; charset="utf-8"'
    )
