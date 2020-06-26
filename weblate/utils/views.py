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
"""Helper methods for views."""

import os
from time import mktime
from zipfile import ZipFile

from django.core.paginator import EmptyPage, Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import http_date
from django.utils.translation import activate
from django.utils.translation import gettext as _
from django.utils.translation import pgettext
from django.views.generic.edit import FormView

from weblate.formats.exporters import get_exporter
from weblate.trans.models import Component, Project, Translation
from weblate.utils import messages


def get_percent_color(percent):
    if percent >= 85:
        return "#2eccaa"
    if percent >= 50:
        return "#38f"
    return "#f6664c"


def get_page_limit(request, default):
    """Return page and limit as integers."""
    try:
        limit = int(request.GET.get("limit", default))
    except ValueError:
        limit = default
    # Cap it to range 10 - 2000
    limit = min(max(10, limit), 2000)
    try:
        page = int(request.GET.get("page", 1))
    except ValueError:
        page = 1
    page = max(1, page)
    return page, limit


def get_paginator(request, object_list, default_page_limit=100):
    """Return paginator and current page."""
    page, limit = get_page_limit(request, default_page_limit)
    paginator = Paginator(object_list, limit)
    try:
        return paginator.page(page)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


class ComponentViewMixin:

    # This should be done in setup once we drop support for older Django
    def get_component(self):
        return get_component(
            self.request, self.kwargs["project"], self.kwargs["component"]
        )


class ProjectViewMixin:
    project = None

    # This should be done in setup once we drop support for older Django
    def dispatch(self, request, *args, **kwargs):
        self.project = get_project(self.request, self.kwargs["project"])
        return super().dispatch(request, *args, **kwargs)


def get_sort_name(request):
    """Gets sort name."""
    sort_dict = {
        "position": _("Position"),
        "priority": _("Priority"),
        "labels": _("Labels"),
        "timestamp": _("Age of string"),
        "num_words": _("Word count"),
        "num_comments": _("Number of comments"),
        "num_failing_checks": _("Number of failing checks"),
        "context": pgettext("Translation key", "Key"),
        "priority,position": _("Position and priority"),
    }
    sort_params = request.GET.get("sort_by", "-priority,position").replace("-", "")
    sort_name = sort_dict.get(sort_params, _("Position and priority"))
    result = {
        "query": request.GET.get("sort_by", "-priority,position"),
        "name": sort_name,
    }
    return result


def get_translation(request, project, component, lang, skip_acl=False):
    """Return translation matching parameters."""
    translation = get_object_or_404(
        Translation.objects.prefetch(),
        language__code=lang,
        component__slug=component,
        component__project__slug=project,
    )

    if not skip_acl:
        request.user.check_access_component(translation.component)
    return translation


def get_component(request, project, component, skip_acl=False):
    """Return component matching parameters."""
    component = get_object_or_404(
        Component.objects.prefetch(), project__slug=project, slug=component,
    )
    if not skip_acl:
        request.user.check_access_component(component)
    return component


def get_project(request, project, skip_acl=False):
    """Return project matching parameters."""
    project = get_object_or_404(Project, slug=project)
    if not skip_acl:
        request.user.check_access(project)
    return project


def get_project_translation(request, project=None, component=None, lang=None):
    """Return project, component, translation tuple for given parameters."""
    if lang and component:
        # Language defined? We can get all
        translation = get_translation(request, project, component, lang)
        component = translation.component
        project = component.project
    else:
        translation = None
        if component:
            # Component defined?
            component = get_component(request, project, component)
            project = component.project
        elif project:
            # Only project defined?
            project = get_project(request, project)

    # Return tuple
    return project or None, component or None, translation or None


def try_set_language(lang):
    """Try to activate language."""
    try:
        activate(lang)
    except Exception:
        # Ignore failure on activating language
        activate("en")


def import_message(request, count, message_none, message_ok):
    if count == 0:
        messages.warning(request, message_none)
    else:
        messages.success(request, message_ok % count)


def iter_files(filenames):
    for filename in filenames:
        if os.path.isdir(filename):
            for root, _unused, files in os.walk(filename):
                if "/.git/" in root or "/.hg/" in root:
                    continue
                yield from (os.path.join(root, name) for name in files)
        else:
            yield filename


def zip_download(root, filenames):
    response = HttpResponse(content_type="application/zip")
    with ZipFile(response, "w") as zipfile:
        for filename in iter_files(filenames):
            with open(filename, "rb") as handle:
                zipfile.writestr(os.path.relpath(filename, root), handle.read())
    response["Content-Disposition"] = 'attachment; filename="translations.zip"'
    return response


def download_translation_file(translation, fmt=None, units=None):
    if fmt is not None:
        try:
            exporter_cls = get_exporter(fmt)
        except KeyError:
            raise Http404("File format not supported")
        if not exporter_cls.supports(translation):
            raise Http404("File format not supported")
        exporter = exporter_cls(translation=translation)
        if units is None:
            units = translation.unit_set.all()
        exporter.add_units(units)
        response = exporter.get_response(
            "{{project}}-{0}-{{language}}.{{extension}}".format(
                translation.component.slug
            )
        )
    else:
        # Force flushing pending units
        translation.commit_pending("download", None)

        filenames = translation.filenames

        if len(filenames) == 1:
            extension = translation.store.extension()
            # Create response
            response = FileResponse(
                open(filenames[0], "rb"), content_type=translation.store.mimetype()
            )
        else:
            extension = "zip"
            response = zip_download(translation.get_filename(), filenames)

        # Construct filename (do not use real filename as it is usually not
        # that useful)
        filename = "{0}-{1}-{2}.{3}".format(
            translation.component.project.slug,
            translation.component.slug,
            translation.language.code,
            extension,
        )

        # Fill in response headers
        response["Content-Disposition"] = "attachment; filename={0}".format(filename)

    if translation.stats.last_changed:
        response["Last-Modified"] = http_date(
            mktime(translation.stats.last_changed.timetuple())
        )

    return response


def show_form_errors(request, form):
    """Show all form errors as a message."""
    for error in form.non_field_errors():
        messages.error(request, error)
    for field in form:
        for error in field.errors:
            messages.error(
                request,
                _("Error in parameter %(field)s: %(error)s")
                % {"field": field.name, "error": error},
            )


class ErrorFormView(FormView):
    def form_invalid(self, form):
        """If the form is invalid, redirect to the supplied URL."""
        show_form_errors(self.request, form)
        return HttpResponseRedirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        """There is no GET view here."""
        return HttpResponseRedirect(self.get_success_url())
