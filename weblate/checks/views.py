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

from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from weblate.checks.models import CHECKS, Check
from weblate.trans.models import Component, Translation, Unit
from weblate.trans.util import redirect_param
from weblate.utils.db import conditional_sum
from weblate.utils.forms import FilterForm
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.views import get_component, get_project


def encode_optional(params):
    if params:
        return f"?{urlencode(params)}"
    return ""


def show_checks(request):
    """List of failing checks."""
    url_params = {}
    user = request.user

    kwargs = {}

    form = FilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("project"):
            kwargs["unit__translation__component__project__slug"] = form.cleaned_data[
                "project"
            ]
            url_params["project"] = form.cleaned_data["project"]

        if form.cleaned_data.get("lang"):
            kwargs["unit__translation__language__code"] = form.cleaned_data["lang"]
            url_params["lang"] = form.cleaned_data["lang"]

        if form.cleaned_data.get("component"):
            kwargs["unit__translation__component__slug"] = form.cleaned_data[
                "component"
            ]
            url_params["component"] = form.cleaned_data["component"]

    allchecks = (
        Check.objects.filter(**kwargs)
        .filter_access(user)
        .values("check")
        .annotate(
            check_count=Count("id"),
            dismissed_check_count=conditional_sum(1, dismissed=True),
            active_check_count=conditional_sum(1, dismissed=False),
            translated_check_count=conditional_sum(
                1, dismissed=False, unit__state__gte=STATE_TRANSLATED
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

    form = FilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("lang"):
            kwargs["component__translation__language__code"] = form.cleaned_data["lang"]
            url_params["lang"] = form.cleaned_data["lang"]

        # This has to be done after updating url_params
        if form.cleaned_data.get("project") and "/" not in form.cleaned_data["project"]:
            return redirect_param(
                "show_check_project",
                encode_optional(url_params),
                project=form.cleaned_data["project"],
                name=name,
            )

    projects = (
        request.user.allowed_projects.filter(**kwargs)
        .annotate(
            check_count=Count("component__translation__unit__check"),
            dismissed_check_count=conditional_sum(
                1, component__translation__unit__check__dismissed=True
            ),
            active_check_count=conditional_sum(
                1, component__translation__unit__check__dismissed=False
            ),
            translated_check_count=conditional_sum(
                1,
                component__translation__unit__check__dismissed=False,
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

    form = FilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("lang"):
            kwargs["translation__language__code"] = form.cleaned_data["lang"]
            url_params["lang"] = form.cleaned_data["lang"]

    components = (
        Component.objects.filter_access(request.user)
        .filter(**kwargs)
        .annotate(
            check_count=Count("translation__unit__check"),
            dismissed_check_count=conditional_sum(
                1, translation__unit__check__dismissed=True
            ),
            active_check_count=conditional_sum(
                1, translation__unit__check__dismissed=False
            ),
            translated_check_count=conditional_sum(
                1,
                translation__unit__check__dismissed=False,
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
            "title": f"{prj}/{check.name}",
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

    if request.GET.get("lang"):
        kwargs["language__code"] = request.GET["lang"]

    translations = (
        Translation.objects.filter(
            component=component, unit__check__check=name, **kwargs
        )
        .annotate(
            check_count=Count("unit__check"),
            dismissed_check_count=conditional_sum(1, unit__check__dismissed=True),
            active_check_count=conditional_sum(1, unit__check__dismissed=False),
            translated_check_count=conditional_sum(
                1, unit__check__dismissed=False, unit__state__gte=STATE_TRANSLATED
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
            "title": f"{component}/{check.name}",
            "check": check,
            "component": component,
        },
    )


def render_check(request, unit_id, check_id):
    """Render endpoint for checks."""
    try:
        obj = Check.objects.get(unit_id=unit_id, check=check_id)
    except Check.DoesNotExist:
        unit = get_object_or_404(Unit, pk=int(unit_id))
        obj = Check(unit=unit, dismissed=False, check=check_id)
    request.user.check_access_component(obj.unit.translation.component)

    return obj.check_obj.render(request, obj.unit)
