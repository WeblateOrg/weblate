# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import activate, gettext, pgettext
from django.views.generic.list import ListView

from weblate.accounts.notifications import NOTIFICATIONS_ACTIONS
from weblate.lang.models import Language
from weblate.trans.forms import ChangesForm
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.models.change import Change
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import PathViewMixin


class ChangesView(PathViewMixin, ListView):
    """Browser for changes."""

    paginate_by = 20
    supported_path_types = (
        None,
        Project,
        Component,
        Translation,
        Language,
        ProjectLanguage,
        Unit,
    )

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["path_object"] = self.path_object

        if isinstance(self.path_object, Unit):
            context["title"] = (
                pgettext(
                    "Changes of string in a translation", "Changes of string in %s"
                )
                % self.path_object
            )
        elif isinstance(self.path_object, Translation):
            context["title"] = (
                pgettext("Changes in translation", "Changes in %s") % self.path_object
            )
        elif isinstance(self.path_object, Component):
            context["title"] = (
                pgettext("Changes in component", "Changes in %s") % self.path_object
            )
        elif isinstance(self.path_object, Project):
            context["title"] = (
                pgettext("Changes in project", "Changes in %s") % self.path_object
            )
        elif isinstance(self.path_object, Language):
            context["title"] = (
                pgettext("Changes in language", "Changes in %s") % self.path_object
            )
        elif isinstance(self.path_object, ProjectLanguage):
            context["title"] = (
                pgettext("Changes in project", "Changes in %s") % self.path_object
            )
        elif self.path_object is None:
            context["title"] = gettext("Changes")
        else:
            raise TypeError(f"Unsupported {self.path_object}")

        if self.path_object is None:
            context["changes_rss"] = reverse("rss")
        else:
            context["changes_rss"] = reverse(
                "rss", kwargs={"path": self.path_object.get_url_path()}
            )

        if self.changes_form.is_valid():
            context["query_string"] = self.changes_form.urlencode()
            context["search_items"] = self.changes_form.items()

        context["form"] = self.changes_form

        return context

    def setup(self, *args, **kwargs):
        super().setup(*args, **kwargs)
        self.changes_form = ChangesForm(data=self.request.GET)

    def get(self, request, *args, **kwargs):
        if self.path_object is None and self.request.GET:
            # Handle GET params for filtering prior Weblate 5.0
            path = None
            if string := self.request.GET.get("string"):
                try:
                    # Check unit access here to avoid leaking project/component
                    unit = Unit.objects.filter_access(self.request.user).get(pk=string)
                except Unit.DoesNotExist:
                    pass
                else:
                    path = unit.get_url_path()
            else:
                path = [
                    request.GET.get("project", "-") or "-",
                    request.GET.get("component", "-") or "-",
                    request.GET.get("lang") or "-",
                ]
                while path and path[-1] == "-":
                    path.pop()
            if path:
                return redirect("changes", path=path)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Return list of changes to browse."""
        filters = {}
        if self.path_object is None:
            params = {}
        elif isinstance(self.path_object, Project):
            params = {"project": self.path_object}
        elif isinstance(self.path_object, Component):
            params = {"component": self.path_object}
        elif isinstance(self.path_object, Translation):
            params = {"translation": self.path_object}
        elif isinstance(self.path_object, Unit):
            params = {"unit": self.path_object}
        elif isinstance(self.path_object, Language):
            params = {"language": self.path_object}
        elif isinstance(self.path_object, ProjectLanguage):
            params = {
                "project": self.path_object.project,
                "language": self.path_object.language,
            }
        else:
            raise TypeError(f"Unsupported {self.path_object}")

        form = self.changes_form
        if form.is_valid():
            if action := form.cleaned_data.get("action"):
                filters["action__in"] = action
            if start_date := form.cleaned_data.get("start_date"):
                filters["timestamp__date__gte"] = start_date
            if end_date := form.cleaned_data.get("end_date"):
                filters["timestamp__date__lte"] = end_date
            if user := form.cleaned_data.get("user"):
                filters["user"] = user

        result = Change.objects.last_changes(self.request.user, **params)

        if filters:
            result = result.filter(**filters)

        return result

    def paginate_queryset(self, queryset, page_size):
        if not self.changes_form.is_valid():
            queryset = queryset.none()
        paginator, page, queryset, is_paginated = super().paginate_queryset(
            queryset, page_size
        )
        page = Change.objects.preload_list(page)
        return paginator, page, queryset, is_paginated


class ChangesCSVView(ChangesView):
    """CSV renderer for changes view."""

    paginate_by = None

    def get(self, request, *args, **kwargs):
        object_list = self.get_queryset()[:2000]

        if not request.user.has_perm("change.download", self.path_object):
            raise PermissionDenied

        # Always output in english
        activate("en")

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = "attachment; filename=changes.csv"

        writer = csv.writer(response)

        # Add header
        writer.writerow(
            ("timestamp", "action", "user", "url", "target", "edit_distance")
        )

        for change in object_list:
            writer.writerow(
                (
                    change.timestamp.isoformat(),
                    change.get_action_display(),
                    change.user.username if change.user else "",
                    get_site_url(change.get_absolute_url()),
                    change.target,
                    change.get_distance(),
                )
            )

        return response


@login_required
def show_change(request, pk):
    change = get_object_or_404(Change, pk=pk)
    acl_obj = change.translation or change.component or change.project
    if not request.user.has_perm("unit.edit", acl_obj):
        raise PermissionDenied
    others = request.GET.getlist("other")
    changes = None
    if others:
        changes = Change.objects.filter(pk__in=[*others, change.pk])
        for change in changes:
            acl_obj = change.translation or change.component or change.project
            if not request.user.has_perm("unit.edit", acl_obj):
                raise PermissionDenied
    if change.action not in NOTIFICATIONS_ACTIONS:
        content = ""
    else:
        notifications = NOTIFICATIONS_ACTIONS[change.action]
        notification = notifications[0](None)
        context = notification.get_context(change if not others else None)
        context["request"] = request
        context["changes"] = changes
        context["subject"] = notification.render_template(
            "_subject.txt", context, digest=bool(others)
        )
        content = notification.render_template(".html", context, digest=bool(others))

    return HttpResponse(content_type="text/html; charset=utf-8", content=content)
