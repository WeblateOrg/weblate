# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helper methods for views."""

from __future__ import annotations

import os
from time import mktime
from typing import Any
from zipfile import ZipFile

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.http import http_date
from django.utils.translation import activate, gettext, gettext_lazy, pgettext_lazy
from django.views.decorators.gzip import gzip_page
from django.views.generic.edit import FormView

from weblate.formats.models import EXPORTERS, FILE_FORMATS
from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation, Unit
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.stats import ProjectLanguage
from weblate.vcs.git import LocalRepository

SORT_KEYS = {
    "name": lambda x: x.name if hasattr(x, "name") else x.component.name,
    "translated": lambda x: x.stats.translated_percent,
    "untranslated": lambda x: x.stats.todo,
    "untranslated_words": lambda x: x.stats.todo_words,
    "untranslated_chars": lambda x: x.stats.todo_chars,
    "nottranslated": lambda x: x.stats.nottranslated,
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


def get_paginator(request, object_list, page_limit=None):
    """Return paginator and current page."""
    page, limit = get_page_limit(request, page_limit or settings.DEFAULT_PAGE_LIMIT)
    sort_by = request.GET.get("sort_by")
    if sort_by:
        object_list, sort_by = sort_objects(object_list, sort_by)
    paginator = Paginator(object_list, limit)
    paginator.sort_by = sort_by
    try:
        return paginator.page(page)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


class PathViewMixin:
    supported_path_types = None

    def get_path_object(self):
        if self.supported_path_types is None:
            raise ValueError("Specifying supported path types is required")
        return parse_path(self.request, self.kwargs["path"], self.supported_path_types)

    def setup(self, request, **kwargs):
        super().setup(request, **kwargs)
        self.component = self.get_path_object()


SORT_CHOICES = {
    "-priority,position": gettext_lazy("Position and priority"),
    "position": gettext_lazy("Position"),
    "priority": gettext_lazy("Priority"),
    "labels": gettext_lazy("Labels"),
    "source": gettext_lazy("Source string"),
    "target": gettext_lazy("Target string"),
    "timestamp": gettext_lazy("String age"),
    "last_updated": gettext_lazy("Last updated"),
    "num_words": gettext_lazy("Number of words"),
    "num_comments": gettext_lazy("Number of comments"),
    "num_failing_checks": gettext_lazy("Number of failing checks"),
    "context": pgettext_lazy("Translation key", "Key"),
    "location": gettext_lazy("String location"),
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
    sort_name = SORT_LOOKUP.get(sort_params, gettext("Position and priority"))
    return {
        "query": sort_query,
        "name": sort_name,
    }


def _parse_path(request, path: tuple[str], *, skip_acl: bool = False):
    path = list(path)
    # First level is always project
    project = get_object_or_404(Project, slug=path.pop(0))
    if not skip_acl:
        request.user.check_access(project)
    project.acting_user = request.user
    if not path:
        return project

    # Project/language special case
    if path[0] == "-" and len(path) == 2:
        language = get_object_or_404(Language, code=path[1])
        return ProjectLanguage(project, language)

    # Component/category structure
    parent = project
    component = None
    while path:
        slug = path.pop(0)
        try:
            component = parent.component_set.get(slug=slug)
        except Component.DoesNotExist as error:
            raise Http404(f"Object {slug} not found in {parent}") from error
        else:
            if not skip_acl:
                request.user.check_access_component(component)
            component.acting_user = request.user
            break

    # Nothing left, return current object
    if not path:
        return component

    if len(path) > 1:
        raise Http404(f"Invalid path left: {'/'.join(path)}")

    return get_object_or_404(component.translation_set, language__code=path[0])


def parse_path(
    request, path: list[str] | None, types: tuple[Any], *, skip_acl: bool = False
):
    if None in types and not path:
        return None
    result = _parse_path(request, path, skip_acl=skip_acl)
    if not isinstance(result, types):
        raise Http404(f"Not supported object type: {result}")
    return result


def parse_path_units(request, path: list[str], types: tuple[Any]):
    obj = parse_path(request, path, types)

    context = {"components": None}
    if isinstance(obj, Translation):
        unit_set = obj.unit_set.all()
        context["translation"] = obj
        context["component"] = obj.component
        context["project"] = obj.component.project
        context["components"] = [obj.component]
    elif isinstance(obj, Component):
        unit_set = Unit.objects.filter(translation__component=obj)
        context["component"] = obj
        context["project"] = obj.project
        context["components"] = [obj]
    elif isinstance(obj, Project):
        unit_set = Unit.objects.filter(translation__component__project=obj)
        context["project"] = obj
    elif isinstance(obj, ProjectLanguage):
        unit_set = Unit.objects.filter(
            translation__component__project=obj.project,
            translation__language=obj.language,
        )
        context["project"] = obj.project
        context["language"] = obj.language
    else:
        raise TypeError("Unsupported result: {obj}")

    return obj, unit_set, context


# TODO: Drop
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


# TODO: Drop
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


# TODO: Drop
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
            project = parse_path(request, [project], (Project,))

    # Return tuple
    return project or None, component or None, translation or None


def guess_filemask_from_doc(data):
    if "filemask" in data:
        return

    ext = ""
    if "docfile" in data and hasattr(data["docfile"], "name"):
        ext = os.path.splitext(os.path.basename(data["docfile"].name))[1]

    if not ext and "file_format" in data and data["file_format"] in FILE_FORMATS:
        ext = FILE_FORMATS[data["file_format"]].extension()

    data["filemask"] = "{}/{}{}".format(data.get("slug", "translations"), "*", ext)


def create_component_from_doc(data):
    # Calculate filename
    uploaded = data["docfile"]
    guess_filemask_from_doc(data)
    filemask = data["filemask"]
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


def zip_download(root: str, filenames: list[str], name: str = "translations"):
    response = HttpResponse(content_type="application/zip")
    with ZipFile(response, "w") as zipfile:
        for filename in iter_files(filenames):
            try:
                with open(filename, "rb") as handle:
                    zipfile.writestr(os.path.relpath(filename, root), handle.read())
            except FileNotFoundError:
                continue
    response["Content-Disposition"] = f'attachment; filename="{name}.zip"'
    return response


@gzip_page
def download_translation_file(
    request,
    translation: Translation,
    fmt: str | None = None,
    query_string: str | None = None,
):
    if fmt is not None:
        try:
            exporter_cls = EXPORTERS[fmt]
        except KeyError as exc:
            raise Http404(f"Conversion to {fmt} is not supported") from exc
        if not exporter_cls.supports(translation):
            raise Http404("File format is not compatible with this translation")
        exporter = exporter_cls(translation=translation)
        units = translation.unit_set.prefetch_full().order_by("position")
        if query_string:
            units = units.search(query_string)
        exporter.add_units(units)
        response = exporter.get_response(
            f"{{project}}-{translation.component.slug}-{{language}}.{{extension}}"
        )
    else:
        # Force flushing pending units
        try:
            translation.commit_pending("download", None)
        except Exception:
            report_error(cause="Download commit", project=translation.component.project)

        filenames = translation.filenames

        if len(filenames) == 1:
            extension = (
                os.path.splitext(translation.filename)[1]
                or f".{translation.component.file_format_cls.extension()}"
            )
            if not os.path.exists(filenames[0]):
                raise Http404("File not found")
            # Create response
            response = FileResponse(
                open(filenames[0], "rb"),  # noqa: SIM115
                content_type=translation.component.file_format_cls.mimetype(),
            )
        else:
            extension = ".zip"
            response = zip_download(
                translation.get_filename(),
                filenames,
                translation.full_slug.replace("/", "-"),
            )

        # Construct filename (do not use real filename as it is usually not
        # that useful)
        project_slug = translation.component.project.slug
        component_slug = translation.component.slug
        language_code = translation.language.code
        filename = f"{project_slug}-{component_slug}-{language_code}{extension}"

        # Fill in response headers
        response["Content-Disposition"] = f"attachment; filename={filename}"

    if translation.stats.last_changed:
        response["Last-Modified"] = http_date(
            mktime(translation.stats.last_changed.timetuple())
        )

    return response


def get_form_errors(form):
    for error in form.non_field_errors():
        yield error
    for field in form:
        for error in field.errors:
            yield gettext("Error in parameter %(field)s: %(error)s") % {
                "field": field.name,
                "error": error,
            }


def show_form_errors(request, form):
    """Show all form errors as a message."""
    for error in get_form_errors(form):
        messages.error(request, error)


class ErrorFormView(FormView):
    def form_invalid(self, form):
        """If the form is invalid, redirect to the supplied URL."""
        show_form_errors(self.request, form)
        return HttpResponseRedirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        """There is no GET view here."""
        return HttpResponseRedirect(self.get_success_url())
