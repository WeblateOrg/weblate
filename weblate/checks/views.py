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

from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.encoding import force_str
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from weblate.checks.models import CHECKS, Check
from weblate.trans.models import Component, Translation
from weblate.trans.util import redirect_param
from weblate.utils.db import conditional_sum
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.views import get_component, get_project


def encode_optional(params):
    if params:
        return "?{0}".format(urlencode(params))
    return ""


def show_checks(request):
    """List of failing checks."""
    url_params = {}
    user = request.user

    kwargs = {
        "unit__translation__component__project_id__in": user.allowed_project_ids,
    }

    if request.GET.get("project"):
        kwargs["unit__translation__component__project__slug"] = request.GET["project"]
        url_params["project"] = request.GET["project"]

    if request.GET.get("language"):
        kwargs["unit__translation__language__code"] = request.GET["language"]
        url_params["language"] = request.GET["language"]

    if request.GET.get("component"):
        kwargs["unit__translation__component__slug"] = request.GET["component"]
        url_params["component"] = request.GET["component"]

    allchecks = (
        Check.objects.filter(**kwargs)
        .values("check")
        .annotate(
            check_count=Count("id"),
            ignored_check_count=conditional_sum(1, ignore=True),
            active_check_count=conditional_sum(1, ignore=False),
            translated_check_count=conditional_sum(
                1, ignore=False, unit__state__gte=STATE_TRANSLATED
            ),
        )
    )

    return render(
        request,
        "checks.html",
        {
            "checks": allchecks,
            "title": _("Failing checks"),
            "url_params": encode_optional(url_params),
        },
    )


def show_check(request, name):
    """Show details about failing check."""
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404("No check matches the given query.")

    url_params = {}

    kwargs = {
        "component__translation__unit__check__check": name,
    }

    if request.GET.get("language"):
        kwargs["component__translation__language__code"] = request.GET["language"]
        url_params["language"] = request.GET["language"]

    # This has to be done after updating url_params
    if request.GET.get("project") and "/" not in request.GET["project"]:
        return redirect_param(
            "show_check_project",
            encode_optional(url_params),
            project=request.GET["project"],
            name=name,
        )

    projects = (
        request.user.allowed_projects.filter(**kwargs)
        .annotate(
            check_count=Count("component__translation__unit__check"),
            ignored_check_count=conditional_sum(
                1, component__translation__unit__check__ignore=True
            ),
            active_check_count=conditional_sum(
                1, component__translation__unit__check__ignore=False
            ),
            translated_check_count=conditional_sum(
                1,
                component__translation__unit__check__ignore=False,
                component__translation__unit__state__gte=STATE_TRANSLATED,
            ),
        )
        .order()
    )

    return render(
        request,
        "check.html",
        {
            "projects": projects,
            "title": check.name,
            "check": check,
            "url_params": encode_optional(url_params),
        },
    )


def show_check_project(request, name, project):
    """Show checks failing in a project."""
    prj = get_project(request, project)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404("No check matches the given query.")

    url_params = {}

    kwargs = {
        "project": prj,
        "translation__unit__check__check": name,
    }

    if request.GET.get("language"):
        kwargs["translation__language__code"] = request.GET["language"]
        url_params["language"] = request.GET["language"]

    components = (
        Component.objects.filter(**kwargs)
        .annotate(
            check_count=Count("translation__unit__check"),
            ignored_check_count=conditional_sum(
                1, translation__unit__check__ignore=True
            ),
            active_check_count=conditional_sum(
                1, translation__unit__check__ignore=False
            ),
            translated_check_count=conditional_sum(
                1,
                translation__unit__check__ignore=False,
                translation__unit__state__gte=STATE_TRANSLATED,
            ),
        )
        .order()
    )

    return render(
        request,
        "check_project.html",
        {
            "components": components,
            "title": "{0}/{1}".format(force_str(prj), check.name),
            "check": check,
            "project": prj,
            "url_params": encode_optional(url_params),
        },
    )


def show_check_component(request, name, project, component):
    """Show checks failing in a component."""
    component = get_component(request, project, component)
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404("No check matches the given query.")

    kwargs = {}

    if request.GET.get("language"):
        kwargs["language__code"] = request.GET["language"]

    translations = (
        Translation.objects.filter(
            component=component, unit__check__check=name, **kwargs
        )
        .annotate(
            check_count=Count("unit__check"),
            ignored_check_count=conditional_sum(1, unit__check__ignore=True),
            active_check_count=conditional_sum(1, unit__check__ignore=False),
            translated_check_count=conditional_sum(
                1, unit__check__ignore=False, unit__state__gte=STATE_TRANSLATED
            ),
        )
        .order_by("language__code")
        .select_related("language")
    )

    return render(
        request,
        "check_component.html",
        {
            "translations": translations,
            "title": "{0}/{1}".format(force_str(component), check.name),
            "check": check,
            "component": component,
        },
    )


def render_check(request, check_id):
    """Render endpoint for checks."""
    obj = get_object_or_404(Check, pk=int(check_id))
    project = obj.unit.translation.component.project
    request.user.check_access(project)

    return obj.check_obj.render(request, obj.unit)
