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

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_cookie

from weblate.lang.models import Language
from weblate.trans.forms import EngageForm
from weblate.trans.models import Component
from weblate.trans.util import render
from weblate.trans.widgets import WIDGETS, SiteOpenGraphWidget
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import get_component, get_project, try_set_language


def widgets_sorter(widget):
    """Provide better ordering of widgets."""
    return WIDGETS[widget].order


def widgets(request, project):
    obj = get_project(request, project)

    # Parse possible language selection
    form = EngageForm(request.user, obj, request.GET)
    lang = None
    component = None
    if form.is_valid():
        if form.cleaned_data["lang"]:
            lang = Language.objects.get(code=form.cleaned_data["lang"]).code
        if form.cleaned_data["component"]:
            component = Component.objects.get(
                slug=form.cleaned_data["component"], project=obj
            ).slug

    kwargs = {"project": obj.slug}
    if lang is not None:
        kwargs["lang"] = lang
    engage_url = get_site_url(reverse("engage", kwargs=kwargs))
    engage_link = mark_safe(
        '<a href="{0}" id="engage-link">{0}</a>'.format(escape(engage_url))
    )
    widget_base_url = get_site_url(reverse("widgets", kwargs={"project": obj.slug}))
    widget_list = []
    for widget_name in sorted(WIDGETS, key=widgets_sorter):
        widget_class = WIDGETS[widget_name]
        if not widget_class.show:
            continue
        color_list = []
        for color in widget_class.colors:
            kwargs = {
                "project": obj.slug,
                "widget": widget_name,
                "color": color,
                "extension": widget_class.extension,
            }
            if lang is not None:
                kwargs["lang"] = lang
            if component is not None:
                kwargs["component"] = component
            color_url = reverse("widget-image", kwargs=kwargs)
            color_list.append({"name": color, "url": get_site_url(color_url)})
        widget_list.append(
            {"name": widget_name, "colors": color_list, "verbose": widget_class.verbose}
        )

    return render(
        request,
        "widgets.html",
        {
            "engage_url": engage_url,
            "engage_link": engage_link,
            "widget_list": widget_list,
            "widget_base_url": widget_base_url,
            "object": obj,
            "project": obj,
            "image_src": widget_list[0]["colors"][0]["url"],
            "form": form,
        },
    )


@vary_on_cookie
@cache_control(max_age=3600)
def render_widget(
    request,
    project,
    widget="287x66",
    color=None,
    lang=None,
    component=None,
    extension="png",
):
    # We intentionally skip ACL here to allow widget sharing
    if component is None:
        obj = get_project(request, project, skip_acl=True)
    elif component == "-":
        project = get_project(request, project, skip_acl=True)
        lang = get_object_or_404(Language, code=lang)
        obj = ProjectLanguage(project, lang)
    else:
        obj = get_component(request, project, component, skip_acl=True)

    # Handle language parameter
    if lang is not None and isinstance(lang, str):
        lang = Language.objects.fuzzy_get(code=lang, strict=True)
        if lang is None:
            raise Http404()
        if "native" not in request.GET:
            try_set_language(lang.code)
    else:
        try_set_language("en")

    # Get widget class
    try:
        widget_class = WIDGETS[widget]
    except KeyError:
        raise Http404()

    # Construct object
    widget_obj = widget_class(obj, color, lang)

    # Redirect widget
    if hasattr(widget_obj, "redirect"):
        return redirect(widget_obj.redirect(), permanent=True)

    # Invalid extension
    if extension != widget_obj.extension or color != widget_obj.color:
        kwargs = {
            "project": project,
            "widget": widget,
            "color": widget_obj.color,
            "extension": widget_obj.extension,
        }
        if lang:
            kwargs["lang"] = lang.code
            return redirect("widget-image", permanent=True, **kwargs)
        return redirect("widget-image", permanent=True, **kwargs)

    # Render widget
    response = HttpResponse(content_type=widget_obj.content_type)
    widget_obj.render(response)
    return response


@vary_on_cookie
@cache_control(max_age=3600)
def render_og(request):
    # Construct object
    widget_obj = SiteOpenGraphWidget()

    # Render widget
    response = HttpResponse(content_type=widget_obj.content_type)
    widget_obj.render(response)
    return response
