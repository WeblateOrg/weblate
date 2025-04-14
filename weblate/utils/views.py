# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helper methods for views."""

from __future__ import annotations

import os
import time
from contextlib import suppress
from typing import TYPE_CHECKING
from zipfile import ZipFile

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.utils.cache import get_conditional_response
from django.utils.http import http_date
from django.utils.translation import activate, gettext, gettext_lazy, pgettext_lazy
from django.views.decorators.gzip import gzip_page
from django.views.generic.base import View
from django.views.generic.edit import FormView

from weblate.formats.models import EXPORTERS, FILE_FORMATS
from weblate.lang.models import Language
from weblate.trans.models import Category, Component, Project, Translation, Unit
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.stats import (
    BaseStats,
    CategoryLanguage,
    ProjectLanguage,
    prefetch_stats,
)
from weblate.vcs.git import LocalRepository

if TYPE_CHECKING:
    from django.db.models import Model

    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.trans.mixins import BaseURLMixin


class UnsupportedPathObjectError(Http404):
    pass


def key_name(instance):
    return instance.name if hasattr(instance, "name") else instance.component.name


def key_translated(instance):
    return instance.stats.translated_percent


def key_untranslated(instance):
    return instance.stats.todo


def key_untranslated_words(instance):
    return instance.stats.todo_words


def key_untranslated_chars(instance):
    return instance.stats.todo_chars


def key_nottranslated(instance):
    return instance.stats.nottranslated


def key_checks(instance):
    return instance.stats.allchecks


def key_suggestions(instance):
    return instance.stats.suggestions


def key_comments(instance):
    return instance.stats.comments


SORT_KEYS = {
    "name": key_name,
    "translated": key_translated,
    "untranslated": key_untranslated,
    "untranslated_words": key_untranslated_words,
    "untranslated_chars": key_untranslated_chars,
    "nottranslated": key_nottranslated,
    "checks": key_checks,
    "suggestions": key_suggestions,
    "comments": key_comments,
}


def optional_form(form, perm_user, perm, perm_obj, **kwargs):
    if not perm_user.has_perm(perm, perm_obj):
        return None
    return form(**kwargs)


def get_percent_color(percent) -> str:
    if percent >= 85:
        return "#2eccaa"
    if percent >= 50:
        return "#38f"
    return "#f6664c"


def get_page_limit(request: AuthenticatedHttpRequest, default: int) -> tuple[int, int]:
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


def get_paginator(
    request: AuthenticatedHttpRequest,
    object_list,
    *,
    page_limit: int | None = None,
    stats: bool = False,
):
    """Return paginator and current page."""
    page, limit = get_page_limit(request, page_limit or settings.DEFAULT_PAGE_LIMIT)
    sort_by = request.GET.get("sort_by")
    stats_fetched = False
    if sort_by:
        # All but ordering by name needs stats
        if sort_by != "name" and stats:
            object_list = prefetch_stats(object_list)
            stats_fetched = True

        object_list, sort_by = sort_objects(object_list, sort_by)
    paginator = Paginator(object_list, limit)
    paginator.sort_by = sort_by
    try:
        result = paginator.page(page)
    except EmptyPage:
        result = paginator.page(paginator.num_pages)

    # Prefetch stats if asked for and were not yet fetched
    if stats and not stats_fetched:
        return prefetch_stats(result)

    return result


class PathViewMixin(View):
    supported_path_types: tuple[type[Model | BaseURLMixin] | None, ...] = ()
    request: AuthenticatedHttpRequest

    def get_path_object(self):
        if not self.supported_path_types:
            msg = "Specifying supported path types is required"
            raise ValueError(msg)
        return parse_path(
            self.request, self.kwargs.get("path", ""), self.supported_path_types
        )

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:  # type: ignore[override]
        super().setup(request, *args, **kwargs)
        self.path_object = self.get_path_object()


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


def get_sort_name(request: AuthenticatedHttpRequest, obj=None):
    """Get sort name."""
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


def parse_path(  # noqa: C901
    request: AuthenticatedHttpRequest | None,
    path: list[str] | tuple[str, ...] | None,
    types: tuple[type[Model | BaseURLMixin] | None, ...],
    *,
    skip_acl: bool = False,
):
    if None in types and not path:
        return None
    if not skip_acl and request is None:
        msg = "Request needs to be provided for ACL check"
        raise TypeError(msg)

    allowed_types = {x for x in types if x is not None}
    acting_user = request.user if request else None

    def check_type(cls) -> None:
        if cls not in allowed_types:
            msg = f"Not supported object type: {cls}"
            raise UnsupportedPathObjectError(msg)

    if path is None:
        msg = "Missing path"
        raise UnsupportedPathObjectError(msg)

    path = list(path)

    # Language URL
    if path[:2] == ["-", "-"] and len(path) == 3:
        if path[2] == "-" and None in types:
            return None
        check_type(Language)
        return get_object_or_404(Language, code=path[2])

    # First level is always project
    project = get_object_or_404(Project, slug=path.pop(0))
    if not skip_acl:
        request.user.check_access(project)
    project.acting_user = acting_user
    if not path:
        check_type(Project)
        return project

    # Project/language special case
    if path[0] == "-" and len(path) == 2:
        check_type(ProjectLanguage)
        language = get_object_or_404(Language, code=path[1])
        return ProjectLanguage(project, language)

    if not allowed_types & {Component, Category, Translation, Unit}:
        msg = "No remaining supported object type"
        raise UnsupportedPathObjectError(msg)

    # Component/category structure
    current: Project | Category | Component = project
    category_args = {"category": None}
    while path:
        slug = path.pop(0)

        # Category/language special case
        if slug == "-" and len(path) == 1:
            language = get_object_or_404(Language, code=path[0])
            check_type(CategoryLanguage)
            return CategoryLanguage(current, language)

        # Try component first
        with suppress(Component.DoesNotExist):
            current = current.component_set.get(slug=slug, **category_args)
            if not skip_acl:
                request.user.check_access_component(current)
            current.acting_user = acting_user
            break

        # Try category
        with suppress(Category.DoesNotExist):
            current = current.category_set.get(slug=slug, **category_args)
            current.acting_user = acting_user
            category_args = {}
            continue

        # Nothing more to try
        msg = f"Object {slug} not found in {current}"
        raise Http404(msg)

    # Nothing left, return current object
    if not path:
        if not isinstance(current, tuple(allowed_types)):
            msg = f"Not supported object type: {current.__class__}"
            raise UnsupportedPathObjectError(msg)
        return current

    if not allowed_types & {Translation, Unit}:
        msg = "No remaining supported object type"
        raise UnsupportedPathObjectError(msg)

    translation = get_object_or_404(current.translation_set, language__code=path.pop(0))
    if not path:
        check_type(Translation)
        return translation

    if len(path) > 1:
        msg = f"Invalid path left: {'/'.join(path)}"
        raise UnsupportedPathObjectError(msg)

    unitid = path.pop(0)

    if not unitid.isdigit():
        msg = f"Invalid unit id: {unitid}"
        raise Http404(msg)

    check_type(Unit)
    return get_object_or_404(translation.unit_set, pk=int(unitid))


def parse_path_units(
    request,
    path: list[str] | tuple[str, ...],
    types: tuple[type[Model | BaseURLMixin] | None, ...],
):
    obj = parse_path(request, path, types)

    context = {"components": None, "path_object": obj}
    if isinstance(obj, Translation):
        unit_set = obj.unit_set.all()
        context["translation"] = obj
        context["component"] = obj.component
        context["project"] = obj.component.project
        context["components"] = [obj.component]
    elif isinstance(obj, Component):
        unit_set = Unit.objects.filter(translation__component=obj).prefetch()
        context["component"] = obj
        context["project"] = obj.project
        context["components"] = [obj]
    elif isinstance(obj, Project):
        unit_set = Unit.objects.filter(translation__component__project=obj).prefetch()
        context["project"] = obj
    elif isinstance(obj, ProjectLanguage):
        unit_set = Unit.objects.filter(
            translation__component__project=obj.project,
            translation__language=obj.language,
        ).prefetch()
        context["project"] = obj.project
        context["language"] = obj.language
    elif isinstance(obj, Category):
        unit_set = Unit.objects.filter(
            translation__component_id__in=obj.all_component_ids
        ).prefetch()
        context["project"] = obj.project
    elif isinstance(obj, CategoryLanguage):
        unit_set = Unit.objects.filter(
            translation__component_id__in=obj.category.all_component_ids,
            translation__language=obj.language,
        ).prefetch()
        context["project"] = obj.category.project
        context["language"] = obj.language
    elif isinstance(obj, Language):
        unit_set = (
            Unit.objects.filter_access(request.user)
            .filter(translation__language=obj)
            .prefetch()
        )
        context["language"] = obj
    elif obj is None:
        unit_set = Unit.objects.filter_access(request.user)
    else:
        msg = f"Unsupported result: {obj}"
        raise TypeError(msg)

    return obj, unit_set, context


def guess_filemask_from_doc(data, docfile=None) -> None:
    if "filemask" in data:
        return

    if docfile is None:
        docfile = data["docfile"]

    ext = ""
    if hasattr(docfile, "name"):
        ext = os.path.splitext(os.path.basename(docfile.name))[1]

    if not ext and "file_format" in data and data["file_format"] in FILE_FORMATS:
        ext = FILE_FORMATS[data["file_format"]].extension()

    data["filemask"] = "{}/{}{}".format(data.get("slug", "translations"), "*", ext)


def create_component_from_doc(data, docfile, target_language: Language | None = None):
    # Calculate filename
    uploaded = docfile or data["docfile"]
    guess_filemask_from_doc(data, uploaded)
    filemask = data["filemask"]
    file_language_code = (
        target_language.code
        if target_language  # bilingual file
        else data["source_language"].code
        if "source_language" in data
        else settings.DEFAULT_LANGUAGE
    )
    filename = filemask.replace("*", file_language_code)
    # Create fake component (needed to calculate path)
    fake = Component(
        project=data["project"],
        slug=data["slug"],
        name=data["name"],
        category=data.get("category", None),
        filemask=filemask,
    )

    if not target_language:
        fake.template = filename

    # Create repository
    LocalRepository.from_files(fake.full_path, {filename: uploaded.read()})
    return fake


def create_component_from_zip(data, zipfile=None):
    # Create fake component (needed to calculate path)
    fake = Component(
        project=data["project"],
        category=data.get("category", None),
        slug=data["slug"],
        name=data["name"],
    )

    # Create repository
    LocalRepository.from_zip(fake.full_path, zipfile or data["zipfile"])
    return fake


def try_set_language(lang) -> None:
    """Try to activate language."""
    try:
        activate(lang)
    except Exception:
        # Ignore failure on activating language
        activate("en")


def import_message(
    request: AuthenticatedHttpRequest, count, message_none, message_ok
) -> None:
    if count == 0:
        messages.warning(request, message_none)
    else:
        try:
            message = message_ok % count
        except TypeError:
            message = message_ok
        messages.success(request, message)


def iter_files(filenames):
    for filename in filenames:
        if os.path.isdir(filename):
            for root, _unused, files in os.walk(filename):
                if "/.git/" in root or "/.hg/" in root:
                    continue
                yield from (os.path.join(root, name) for name in files)
        else:
            yield filename


def zip_download(
    root: str,
    filenames: list[str],
    name: str = "translations",
    extra: dict[str, bytes | str] | None = None,
):
    response = HttpResponse(content_type="application/zip")
    with ZipFile(response, "w", strict_timestamps=False) as zipfile:
        for filename in iter_files(filenames):
            try:
                zipfile.write(filename, arcname=os.path.relpath(filename, root))
            except FileNotFoundError:
                continue
        if extra:
            for filename, content in extra.items():
                zipfile.writestr(filename, content)
    response["Content-Disposition"] = f'attachment; filename="{name}.zip"'
    return response


def handle_last_modified(
    request: HttpRequest, stats: BaseStats
) -> HttpResponseBase | None:
    last_modified = stats.last_changed
    if not last_modified:
        return None
    # Respond with 302/412 response if needed
    return get_conditional_response(
        request,
        last_modified=int(last_modified.timestamp()),
    )


@gzip_page
def download_translation_file(
    request,
    translation: Translation,
    fmt: str | None = None,
    query_string: str | None = None,
):
    response = handle_last_modified(request, translation.stats)
    if response is not None:
        return response

    if fmt is not None:
        try:
            exporter_cls = EXPORTERS[fmt]
        except KeyError as exc:
            msg = f"Conversion to {fmt} is not supported"
            raise Http404(msg) from exc
        if not exporter_cls.supports(translation):
            msg = "File format is not compatible with this translation"
            raise Http404(msg)
        exporter = exporter_cls(translation=translation)
        units = translation.unit_set.prefetch_full().order_by("position")
        if query_string:
            units = units.search(query_string)
        exporter.add_units(units)
        response = exporter.get_response()
    else:
        # Force flushing pending units
        try:
            translation.commit_pending("download", None)
        except Exception:
            report_error("Download commit", project=translation.component.project)

        filenames = translation.filenames

        if len(filenames) == 1:
            extension = (
                os.path.splitext(translation.filename)[1]
                or f".{translation.component.file_format_cls.extension()}"
            )
            if not os.path.exists(filenames[0]):
                msg = "File not found"
                raise Http404(msg)
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

    # Last-Modified timestamp
    if last_changed := translation.stats.last_changed:
        last_modified = last_changed.timestamp()
    else:
        # Use current timestamp if stats do not have any
        last_modified = time.time()
    response["Last-Modified"] = http_date(int(last_modified))

    return response


def get_form_data(data: dict[str, str | int | None]) -> dict[str, str | int]:
    return {key: "" if value is None else value for key, value in data.items()}


def get_form_errors(form):
    for error in form.non_field_errors():
        yield error
    for field in form:
        for error in field.errors:
            yield gettext("Error in parameter %(field)s: %(error)s") % {
                "field": field.name,
                "error": error,
            }


def show_form_errors(request: AuthenticatedHttpRequest, form) -> None:
    """Show all form errors as a message."""
    for error in get_form_errors(form):
        messages.error(request, error)


class ErrorFormView(FormView):
    request: AuthenticatedHttpRequest

    def form_invalid(self, form):
        """If the form is invalid, redirect to the supplied URL."""
        show_form_errors(self.request, form)
        return HttpResponseRedirect(self.get_success_url())

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        """There is no GET view here."""
        return HttpResponseRedirect(self.get_success_url())
