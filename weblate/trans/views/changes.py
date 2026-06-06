# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import feedgenerator
from django.utils.html import format_html
from django.utils.translation import activate, get_language, gettext, pgettext
from django.views.generic.list import ListView

from weblate.accounts.notifications import NOTIFICATIONS_ACTIONS
from weblate.lang.models import Language
from weblate.trans.feeds import get_change_feed_guid
from weblate.trans.forms import ChangesForm
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.trans.models.change import Change
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectLanguage
from weblate.utils.views import PathViewMixin
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from django.db.models import Model

    from weblate.auth.models import AuthenticatedHttpRequest


class ChangesView(PathViewMixin, ListView):
    """Browser for changes."""

    paginate_by: int | None = 20
    supported_path_types = (
        None,
        Project,
        Component,
        Translation,
        Language,
        ProjectLanguage,
        Unit,
        Workspace,
    )

    def get_changes_url(self, url_name: str = "changes") -> str:
        if self.path_object is None:
            return reverse(url_name)
        return reverse(url_name, kwargs={"path": self.path_object.get_url_path()})

    def get_filtered_changes_url(self) -> str:
        url = self.get_changes_url()
        if self.changes_form.is_valid() and (
            query_string := self.changes_form.urlencode()
        ):
            return f"{url}?{query_string}"
        return url

    def get_title(self):
        if isinstance(self.path_object, Unit):
            return (
                pgettext(
                    "Changes of string in a translation", "Changes of string in %s"
                )
                % self.path_object
            )
        if isinstance(self.path_object, Translation):
            return (
                pgettext("Changes in translation", "Changes in %s") % self.path_object
            )
        if isinstance(self.path_object, Component):
            return pgettext("Changes in component", "Changes in %s") % self.path_object
        if isinstance(self.path_object, Project):
            return pgettext("Changes in project", "Changes in %s") % self.path_object
        if isinstance(self.path_object, Language):
            return pgettext("Changes in language", "Changes in %s") % self.path_object
        if isinstance(self.path_object, ProjectLanguage):
            return pgettext("Changes in project", "Changes in %s") % self.path_object
        if isinstance(self.path_object, Workspace):
            return pgettext("Changes in workspace", "Changes in %s") % self.path_object
        if self.path_object is None:
            return gettext("Changes")
        msg = f"Unsupported {self.path_object}"
        raise TypeError(msg)

    def get_template_names(self):
        if digest := self.request.GET.get("digest"):
            if digest in {"pending_suggestions", "todo_strings"}:
                return [f"mail/{digest}.html"]
            return ["mail/digest.html"]
        return super().get_template_names()

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["path_object"] = self.path_object
        context["title"] = self.get_title()
        context["changes_rss"] = self.get_changes_url("changes-rss")

        if self.changes_form.is_valid():
            context["query_string"] = self.changes_form.urlencode()
            context["search_items"] = self.changes_form.items()
            if period := self.changes_form.cleaned_data.get("period"):
                self.changes_form.fields["period"].widget.attrs["data-start-date"] = (
                    period["start_date"].strftime("%m/%d/%Y")
                )
                self.changes_form.fields["period"].widget.attrs["data-end-date"] = (
                    period["end_date"].strftime("%m/%d/%Y")
                )

        context["form"] = self.changes_form

        # Compatibility with digest templates
        context["changes"] = context["object_list"]
        context["subject"] = "Digest preview"

        return context

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        self.changes_form = ChangesForm(data=self.request.GET)

    def get_request_param(self, request: AuthenticatedHttpRequest, param: str) -> str:
        value = request.GET.get(param)
        if not value or "/" in value:
            return "-"
        return value

    def get(  # type: ignore[override]
        self, request: AuthenticatedHttpRequest, *args, **kwargs
    ):
        if self.path_object is None and self.request.GET:
            # Handle GET params for filtering prior Weblate 5.0
            path = None
            string = self.request.GET.get("string")
            if string and string.isdigit():
                try:
                    # Check unit access here to avoid leaking project/component
                    unit = Unit.objects.filter_access(self.request.user).get(pk=string)
                except Unit.DoesNotExist:
                    pass
                else:
                    path = unit.get_url_path()
            else:
                path = [
                    self.get_request_param(request, "project"),
                    self.get_request_param(request, "component"),
                    self.get_request_param(request, "lang"),
                ]
                while path and path[-1] == "-":
                    path.pop()
            if path:
                try:
                    return redirect("changes", path=path)
                except NoReverseMatch:
                    return redirect("changes")
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Return list of changes to browse."""
        filters = {}
        excludes = {}
        params: dict[str, Model]
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
        elif isinstance(self.path_object, Workspace):
            params = {"workspace": self.path_object}
        else:
            msg = f"Unsupported {self.path_object}"
            raise TypeError(msg)

        form = self.changes_form
        if form.is_valid():
            if action := form.cleaned_data.get("action"):
                filters["action__in"] = action
            if period := form.cleaned_data.get("period"):
                # start_date and end_date are datetime objects
                filters["timestamp__gte"] = period["start_date"]
                filters["timestamp__lte"] = period["end_date"]
            if user := form.cleaned_data.get("user"):
                filters["user"] = user
            # If we are filtering all the entries by one user, all
            # other users are excluded by default, so we don't need
            # to set this exclude.
            elif exclude_user := form.cleaned_data.get("exclude_user"):
                excludes["user"] = exclude_user

        result = Change.objects.last_changes(self.request.user, **params)

        if filters:
            result = result.filter(**filters)
        if excludes:
            result = result.exclude(**excludes)

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

    def get(  # type: ignore[override]
        self, request: AuthenticatedHttpRequest, *args, **kwargs
    ):
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
            ("timestamp", "action", "user", "url", "target", "edit_distance", "message")
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
                    change.message,
                )
            )

        return response


class ChangesRSSView(ChangesView):
    """RSS renderer for changes view."""

    feed_count = 10
    paginate_by = None

    def get_feed_title(self):
        if self.path_object is None:
            # Translators: %s is site title here
            return gettext("Recent changes on %s") % settings.SITE_TITLE
        # Translators: %s is translation/project/component/language name
        return gettext("Recent changes in %s") % self.path_object

    def get_feed_description(self):
        if self.path_object is None:
            # Translators: %s is site title here
            return gettext("All recent changes made using Weblate on %s.") % (
                settings.SITE_TITLE
            )
        # Translators: %s is translation/project/component/language name
        return (
            gettext("All recent changes made using Weblate in %s.") % self.path_object
        )

    def get(  # type: ignore[override]
        self, request: AuthenticatedHttpRequest, *args, **kwargs
    ):
        if self.changes_form.is_valid():
            object_list = Change.objects.preload_list(
                list(self.get_queryset()[: self.feed_count])
            )
        else:
            object_list = []

        feed = feedgenerator.Rss201rev2Feed(
            title=self.get_feed_title(),
            link=get_site_url(self.get_filtered_changes_url()),
            description=self.get_feed_description(),
            language=get_language(),
            feed_url=get_site_url(request.get_full_path()),
        )

        for change in object_list:
            link = get_site_url(change.get_absolute_url())
            feed.add_item(
                title=change.get_action_display(),
                link=link,
                description=str(change),
                author_name=change.get_user_display(False),
                pubdate=change.timestamp,
                unique_id=get_change_feed_guid(change),
                unique_id_is_permalink=False,
            )

        response = HttpResponse(content_type=feed.content_type)
        feed.write(response, "utf-8")
        return response


@login_required
def show_change(request: AuthenticatedHttpRequest, pk: int):
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

    # If the change carries a user-provided message, surface it prominently
    # at the top of the detail view so reviewers cannot miss it.
    message_html = ""
    if change.message:
        message_html = format_html(
            '<div class="alert alert-info change-user-message" role="alert">'
            '<span class="fw-semibold">{label}</span> {message}'
            "</div>",
            label=gettext("Note:"),
            message=change.message,
        )

    return HttpResponse(
        content_type="text/html; charset=utf-8",
        content=str(message_html) + content,
    )
