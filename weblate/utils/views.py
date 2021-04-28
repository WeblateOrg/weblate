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
"""Helper methods for views."""

import os
from time import mktime
from zipfile import ZipFile

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import http_date
from django.utils.translation import activate
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from django.views.decorators.gzip import gzip_page
from django.views.generic.edit import FormView

from weblate.formats.models import EXPORTERS
from weblate.trans.models import Component, Project, Translation
from weblate.utils import messages
from weblate.vcs.git import LocalRepository

SORT_KEYS = {
    "name": lambda x: x.name if hasattr(x, "name") else x.component.name,
    "translated": lambda x: x.stats.translated_percent,
    "untranslated": lambda x: x.stats.todo,
    "untranslated_words": lambda x: x.stats.todo_words,
    "untranslated_chars": lambda x: x.stats.todo_chars,
    "checks": lambda x: x.stats.allchecks,
    "suggestions": lambda x: x.stats.suggestions,
    "comments": lambda x: x.stats.comments,
}


def optional_form(form, perm_user, perm, perm_obj, **kwargs):
    if not perm_user.has_perm(perm, perm_obj):
        return None
    return form(**kwargs)


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


def sort_objects(object_list, sort_by: str):
    if sort_by.startswith("-"):
        sort_key = sort_by[1:]
        reverse = True
    else:
        sort_key = sort_by
        reverse = False
    try:
        key = SORT_KEYS[sort_key]
    except KeyError:
        return object_list, None
    return sorted(object_list, key=key, reverse=reverse), sort_by


def get_paginator(request, object_list, default_page_limit=100):
    """Return paginator and current page."""
    page, limit = get_page_limit(request, default_page_limit)
    sort_by = request.GET.get("sort_by")
    if sort_by:
        object_list, sort_by = sort_objects(object_list, sort_by)
    paginator = Paginator(object_list, limit)
    paginator.sort_by = sort_by
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


SORT_CHOICES = {
    "-priority,position": gettext_lazy("Position and priority"),
    "position": gettext_lazy("Position"),
    "priority": gettext_lazy("Priority"),
    "labels": gettext_lazy("Labels"),
    "source": gettext_lazy("Source string"),
    "target": gettext_lazy("Translated string"),
    "timestamp": gettext_lazy("Age of string"),
    "num_words": gettext_lazy("Number of words"),
    "num_comments": gettext_lazy("Number of comments"),
    "num_failing_checks": gettext_lazy("Number of failing checks"),
    "context": pgettext_lazy("Translation key", "Key"),
}

SORT_LOOKUP = {key.replace("-", ""): value for key, value in SORT_CHOICES.items()}


def get_sort_name(request, obj=None):
    """Gets sort name."""
    if hasattr(obj, "component") and obj.component.is_glossary:
        default = "source"
    else:
        default = "-priority,position"
    sort_query = request.GET.get("sort_by", default)
    sort_params = sort_query.replace("-", "")
    sort_name = SORT_LOOKUP.get(sort_params, _("Position and priority"))
    return {
        "query": sort_query,
        "name": sort_name,
    }


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
        Component.objects.prefetch(),
        project__slug=project,
        slug=component,
    )
    if not skip_acl:
        request.user.check_access_component(component)
    component.acting_user = request.user
    return component


def get_project(request, project, skip_acl=False):
    """Return project matching parameters."""
    project = get_object_or_404(Project, slug=project)
    if not skip_acl:
        request.user.check_access(project)
    project.acting_user = request.user
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


def create_component_from_doc(data):
    # Calculate filename
    uploaded = data["docfile"]
    ext = os.path.splitext(os.path.basename(uploaded.name))[1]
    filemask = "{}/{}{}".format(data["slug"], "*", ext)
    filename = filemask.replace(
        "*",
        data["source_language"].code
        if "source_language" in data
        else settings.DEFAULT_LANGUAGE,
    )
    # Create fake component (needed to calculate path)
    fake = Component(
        project=data["project"],
        slug=data["slug"],
        name=data["name"],
        template=filename,
        filemask=filemask,
    )
    # Create repository
    LocalRepository.from_files(fake.full_path, {filename: uploaded.read()})
    return fake


def create_component_from_zip(data):
    # Create fake component (needed to calculate path)
    fake = Component(
        project=data["project"],
        slug=data["slug"],
        name=data["name"],
    )

    # Create repository
    LocalRepository.from_zip(fake.full_path, data["zipfile"])
    return fake


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


def zip_download(root, filenames, name="translations"):
    response = HttpResponse(content_type="application/zip")
    with ZipFile(response, "w") as zipfile:
        for filename in iter_files(filenames):
            with open(filename, "rb") as handle:
                zipfile.writestr(os.path.relpath(filename, root), handle.read())
    response["Content-Disposition"] = f'attachment; filename="{name}.zip"'
    return response


@gzip_page
def download_translation_file(request, translation, fmt=None, units=None):
    if fmt is not None:
        try:
            exporter_cls = EXPORTERS[fmt]
        except KeyError:
            raise Http404("File format not supported")
        if not exporter_cls.supports(translation):
            raise Http404("File format not supported")
        exporter = exporter_cls(translation=translation)
        if units is None:
            units = translation.unit_set.prefetch_full().order_by("position")
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
            extension = translation.component.file_format_cls.extension()
            # Create response
            response = FileResponse(
                open(filenames[0], "rb"),
                content_type=translation.component.file_format_cls.mimetype(),
            )
        else:
            extension = "zip"
            response = zip_download(
                translation.get_filename(),
                filenames,
                translation.full_slug.replace("/", "-"),
            )

        # Construct filename (do not use real filename as it is usually not
        # that useful)
        filename = "{}-{}-{}.{}".format(
            translation.component.project.slug,
            translation.component.slug,
            translation.language.code,
            extension,
        )

        # Fill in response headers
        response["Content-Disposition"] = f"attachment; filename={filename}"

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
