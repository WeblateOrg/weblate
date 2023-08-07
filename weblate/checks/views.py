# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.http import urlencode
from django.utils.translation import gettext

from weblate.checks.models import CHECKS, Check
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.util import redirect_param
from weblate.utils.db import conditional_sum
from weblate.utils.forms import FilterForm
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.views import parse_path, show_form_errors


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
    else:
        show_form_errors(request, form)

    allchecks = (
        Check.objects.filter(**kwargs)
        .filter_access(user)
        .values("name")
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
            "title": gettext("Failing checks"),
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
        "component__translation__unit__check__name": name,
    }

    form = FilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("lang"):
            kwargs["component__translation__language__code"] = form.cleaned_data["lang"]
            url_params["lang"] = form.cleaned_data["lang"]

        # This has to be done after updating url_params
        if form.cleaned_data.get("project") and "/" not in form.cleaned_data["project"]:
            return redirect_param(
                "show_check_path",
                encode_optional(url_params),
                path=[form.cleaned_data["project"]],
                name=name,
            )
    else:
        show_form_errors(request, form)

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


def show_check_path(request, name, path):
    try:
        check = CHECKS[name]
    except KeyError:
        raise Http404("No check matches the given query.")
    obj = parse_path(request, path, (Component, Project))
    if isinstance(obj, Project):
        return show_check_project(request, check, obj)
    return show_check_component(request, check, obj)


def show_check_project(request, check, project):
    """Show checks failing in a project."""
    url_params = {}

    kwargs = {
        "project": project,
        "translation__unit__check__name": check.name,
    }

    form = FilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("lang"):
            kwargs["translation__language__code"] = form.cleaned_data["lang"]
            url_params["lang"] = form.cleaned_data["lang"]
    else:
        show_form_errors(request, form)

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
            "title": f"{project}/{check.name}",
            "check": check,
            "project": project,
            "url_params": encode_optional(url_params),
        },
    )


def show_check_component(request, check, component):
    """Show checks failing in a component."""
    kwargs = {}

    form = FilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("lang"):
            kwargs["language__code"] = form.cleaned_data["lang"]
    else:
        show_form_errors(request, form)

    translations = (
        Translation.objects.filter(
            component=component, unit__check__name=check.name, **kwargs
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
        obj = Check.objects.get(unit_id=unit_id, name=check_id)
    except Check.DoesNotExist:
        unit = get_object_or_404(Unit, pk=int(unit_id))
        obj = Check(unit=unit, dismissed=False, name=check_id)
    request.user.check_access_component(obj.unit.translation.component)

    return obj.check_obj.render(request, obj.unit)
