#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.machinery.base import MachineTranslationError
from weblate.trans.models import Change, Unit
from weblate.trans.util import sort_unicode
from weblate.utils.errors import report_error
from weblate.utils.views import get_component, get_project, get_translation


def handle_machinery(request, service, unit, search=None):
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
            response["responseDetails"] = f"{error.__class__.__name__}: {error}"

    if response["responseStatus"] != 200:
        unit.translation.log_info("machinery failed: %s", response["responseDetails"])

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
    user = request.user
    user.check_access_component(unit.translation.component)

    return render(
        request,
        "js/translations.html",
        {
            "units": sort_unicode(
                unit.source_unit.unit_set.exclude(pk=unit.pk)
                .prefetch()
                .prefetch_full(),
                lambda unit: "{}-{}".format(
                    user.profile.get_translation_order(unit.translation),
                    unit.translation.language,
                ),
            ),
            "component": unit.translation.component,
        },
    )


@require_POST
@login_required
def ignore_check(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))

    if not request.user.has_perm("unit.check", obj):
        raise PermissionDenied()

    # Mark check for ignoring
    obj.set_dismiss("revert" not in request.GET)
    # response for AJAX
    return HttpResponse("ok")


@require_POST
@login_required
def ignore_check_source(request, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    unit = obj.unit.source_unit

    if not request.user.has_perm("unit.check", obj) or not request.user.has_perm(
        "source.edit", unit.translation.component
    ):
        raise PermissionDenied()

    # Mark check for ignoring
    ignore = obj.check_obj.ignore_string
    flags = Flags(unit.extra_flags)
    if ignore not in flags:
        flags.merge(ignore)
        unit.extra_flags = flags.format()
        unit.save(same_content=True)

    # response for AJAX
    return HttpResponse("ok")


def git_status_shared(request, obj, repositories):
    if not request.user.has_perm("meta:vcs.status", obj):
        raise PermissionDenied()

    changes = obj.change_set.filter(action__in=Change.ACTIONS_REPOSITORY).order()[:10]

    return render(
        request,
        "js/git-status.html",
        {
            "object": obj,
            "changes": changes.prefetch(),
            "repositories": repositories,
            "pending_units": obj.count_pending_units,
            "outgoing_commits": sum(repo.count_repo_outgoing for repo in repositories),
            "missing_commits": sum(repo.count_repo_missing for repo in repositories),
        },
    )


@login_required
def git_status_project(request, project):
    obj = get_project(request, project)

    return git_status_shared(request, obj, obj.all_repo_components)


@login_required
def git_status_component(request, project, component):
    obj = get_component(request, project, component)

    target = obj
    if target.is_repo_link:
        target = target.linked_component

    return git_status_shared(request, obj, [obj])


@login_required
def git_status_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    target = obj.component
    if target.is_repo_link:
        target = target.linked_component

    return git_status_shared(request, obj, [obj.component])


@cache_control(max_age=3600)
def matomo(request):
    return render(
        request, "js/matomo.js", content_type='text/javascript; charset="utf-8"'
    )
