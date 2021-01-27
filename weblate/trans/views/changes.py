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

import csv

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import activate
from django.utils.translation import gettext as _
from django.utils.translation import pgettext
from django.views.generic.list import ListView

from weblate.accounts.notifications import NOTIFICATIONS_ACTIONS
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.forms import ChangesForm
from weblate.trans.models.change import Change
from weblate.utils import messages
from weblate.utils.forms import FilterForm
from weblate.utils.site import get_site_url
from weblate.utils.views import get_project_translation, show_form_errors


class ChangesView(ListView):
    """Browser for changes."""

    paginate_by = 20

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.project = None
        self.component = None
        self.translation = None
        self.language = None
        self.user = None
        self.actions = set()

    def get_context_data(self, **kwargs):
        """Create context for rendering page."""
        context = super().get_context_data(**kwargs)
        context["project"] = self.project

        url = {}

        if self.translation is not None:
            context["project"] = self.translation.component.project
            context["component"] = self.translation.component
            context["translation"] = self.translation
            url["lang"] = self.translation.language.code
            url["component"] = self.translation.component.slug
            url["project"] = self.translation.component.project.slug
            context["changes_rss"] = reverse("rss-translation", kwargs=url)
            context["title"] = (
                pgettext("Changes in translation", "Changes in %s") % self.translation
            )
        elif self.component is not None:
            context["project"] = self.component.project
            context["component"] = self.component
            url["component"] = self.component.slug
            url["project"] = self.component.project.slug
            context["changes_rss"] = reverse("rss-component", kwargs=url)
            context["title"] = (
                pgettext("Changes in component", "Changes in %s") % self.component
            )
        elif self.project is not None:
            context["project"] = self.project
            url["project"] = self.project.slug
            context["changes_rss"] = reverse("rss-project", kwargs=url)
            context["title"] = (
                pgettext("Changes in project", "Changes in %s") % self.project
            )

        if self.language is not None:
            context["language"] = self.language
            url["lang"] = self.language.code
            if "changes_rss" not in context:
                context["changes_rss"] = reverse("rss-language", kwargs=url)
            if "title" not in context:
                context["title"] = (
                    pgettext("Changes in language", "Changes in %s") % self.language
                )

        if self.user is not None:
            context["changes_user"] = self.user
            url["user"] = self.user.username
            if "title" not in context:
                context["title"] = (
                    pgettext("Changes by user", "Changes by %s") % self.user.full_name
                )

        url = list(url.items())
        for action in self.actions:
            url.append(("action", action))

        if not url:
            context["changes_rss"] = reverse("rss")

        context["query_string"] = urlencode(url)

        context["form"] = ChangesForm(self.request, data=self.request.GET)

        context["search_items"] = url

        return context

    def _get_queryset_project(self, form):
        """Filtering by translation/project."""
        if not form.cleaned_data.get("project"):
            return
        try:
            self.project, self.component, self.translation = get_project_translation(
                self.request,
                form.cleaned_data.get("project"),
                form.cleaned_data.get("component"),
                form.cleaned_data.get("lang"),
            )
        except Http404:
            messages.error(self.request, _("Failed to find matching project!"))

    def _get_queryset_language(self, form):
        """Filtering by language."""
        if self.translation is None and form.cleaned_data.get("lang"):
            try:
                self.language = Language.objects.get(code=form.cleaned_data["lang"])
            except Language.DoesNotExist:
                messages.error(self.request, _("Failed to find matching language!"))

    def _get_queryset_user(self, form):
        """Filtering by user."""
        if form.cleaned_data.get("user"):
            try:
                self.user = User.objects.get(username=form.cleaned_data["user"])
            except User.DoesNotExist:
                messages.error(self.request, _("Failed to find matching user!"))

    def _get_request_actions(self):
        form = ChangesForm(self.request, data=self.request.GET)
        if form.is_valid() and "action" in form.cleaned_data:
            self.actions.update(form.cleaned_data["action"])

    def get_queryset(self):
        """Return list of changes to browse."""
        form = FilterForm(self.request.GET)
        if form.is_valid():
            self._get_queryset_project(form)

            self._get_queryset_language(form)

            self._get_queryset_user(form)

            self._get_request_actions()
        else:
            show_form_errors(self.request, form)

        result = Change.objects.last_changes(self.request.user)

        if self.translation is not None:
            result = result.filter(translation=self.translation)
        elif self.component is not None:
            result = result.filter(component=self.component)
        elif self.project is not None:
            result = result.filter(project=self.project)

        if self.language is not None:
            result = result.filter(language=self.language)

        if self.actions:
            result = result.filter(action__in=self.actions)

        if self.user is not None:
            result = result.filter(user=self.user)

        return result


class ChangesCSVView(ChangesView):
    """CSV renderer for changes view."""

    paginate_by = None

    def get(self, request, *args, **kwargs):
        object_list = self.get_queryset()[:2000]

        # Do reasonable ACL check for global
        acl_obj = self.translation or self.component or self.project
        if not acl_obj:
            for change in object_list:
                if change.component:
                    acl_obj = change.component
                    break

        if not request.user.has_perm("change.download", acl_obj):
            raise PermissionDenied()

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
        raise PermissionDenied()
    others = request.GET.getlist("other")
    changes = None
    if others:
        changes = Change.objects.filter(pk__in=others + [change.pk])
        for change in changes:
            acl_obj = change.translation or change.component or change.project
            if not request.user.has_perm("unit.edit", acl_obj):
                raise PermissionDenied()
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
