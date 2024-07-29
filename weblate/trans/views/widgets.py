# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_cookie
from django.views.generic import RedirectView

from weblate.lang.models import Language
from weblate.trans.forms import EngageForm
from weblate.trans.models import Component, Project, Translation
from weblate.trans.util import render
from weblate.trans.widgets import WIDGETS, OpenGraphWidget
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import parse_path, show_form_errors, try_set_language

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def widgets_sorter(widget):
    """Provide better ordering of widgets."""
    return WIDGETS[widget].order


def widgets(request: AuthenticatedHttpRequest, path: list[str]):
    engage_obj = project = parse_path(request, path, (Project,))

    # Parse possible language selection
    form = EngageForm(request.user, project, request.GET)
    lang = None
    component = None
    if form.is_valid():
        lang = form.cleaned_data["lang"]
        component = form.cleaned_data["component"]
    else:
        show_form_errors(request, form)

    if component:
        if lang:
            try:
                obj = component.translation_set.get(language=lang)
            except Translation.DoesNotExist:
                obj = component
            engage_obj = ProjectLanguage(project=component.project, language=lang)
        else:
            obj = component
    elif lang:
        engage_obj = obj = ProjectLanguage(project=project, language=lang)
    else:
        obj = project

    engage_url = get_site_url(
        reverse("engage", kwargs={"path": engage_obj.get_url_path()})
    )
    engage_link = format_html('<a href="{0}" id="engage-link">{0}</a>', engage_url)
    widget_base_url = get_site_url(
        reverse("widgets", kwargs={"path": project.get_url_path()})
    )
    widget_list = []
    for widget_name in sorted(WIDGETS, key=widgets_sorter):
        widget_class = WIDGETS[widget_name]
        color_list = []
        for color in widget_class.colors:
            color_url = reverse(
                "widget-image",
                kwargs={
                    "path": obj.get_url_path(),
                    "widget": widget_name,
                    "color": color,
                    "extension": widget_class.extension,
                },
            )
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
            "project": project,
            "image_src": widget_list[0]["colors"][0]["url"],
            "form": form,
        },
    )


class WidgetRedirectView(RedirectView):
    permanent = True
    query_string = True

    def get_redirect_url(
        self,
        project: str,
        widget: str,
        color: str,
        extension: str,
        lang: str | None = None,
        component: str | None = None,
    ):
        path = [project]
        if component:
            path.append(component)
        if lang:
            if not component:
                path.append("-")
            path.append(lang)
        # Redirect no longer supported badge styles to svg
        if widget == "shields":
            widget = "svg"
        return reverse(
            "widget-image",
            kwargs={
                "color": color,
                "extension": extension,
                "widget": widget,
                "path": path,
            },
        )


@vary_on_cookie
@cache_control(max_age=3600)
def render_widget(
    request: AuthenticatedHttpRequest,
    path: list[str],
    widget: str,
    color: str,
    extension: str,
):
    # We intentionally skip ACL here to allow widget sharing
    obj = parse_path(
        request,
        path,
        (Component, ProjectLanguage, Project, Translation, Language, None),
        skip_acl=True,
    )
    lang = set_lang = None
    if isinstance(obj, Language):
        set_lang = obj
    elif hasattr(obj, "language"):
        set_lang = lang = obj.language
    if isinstance(obj, Translation):
        obj = obj.component
    if isinstance(obj, ProjectLanguage):
        obj = obj.project

    if set_lang:
        if "native" not in request.GET:
            try_set_language(set_lang.code)
    else:
        try_set_language("en")

    # Get widget class
    try:
        widget_class = WIDGETS[widget]
    except KeyError as error:
        raise Http404 from error

    # Construct object
    widget_obj = widget_class(obj, color, lang)

    # Invalid extension
    if extension != widget_obj.extension or color != widget_obj.color:
        kwargs = {
            "path": path,
            "widget": widget,
            "color": widget_obj.color,
            "extension": widget_obj.extension,
        }
        return redirect("widget-image", permanent=True, **kwargs)

    # Render widget
    response = HttpResponse(content_type=widget_obj.content_type)
    widget_obj.render(response)
    return response


@vary_on_cookie
@cache_control(max_age=3600)
def render_og(request: AuthenticatedHttpRequest):
    # Construct object
    widget_obj = OpenGraphWidget(None)

    # Render widget
    response = HttpResponse(content_type=widget_obj.content_type)
    widget_obj.render(response)
    return response
