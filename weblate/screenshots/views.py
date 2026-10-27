# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import difflib
import os
from typing import TYPE_CHECKING, ClassVar, cast

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse, JsonResponse, QueryDict
from django.shortcuts import aget_object_or_404, get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.translation import gettext, ngettext
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DetailView, ListView
from PIL import Image

from weblate.screenshots.forms import (
    ScreenshotEditForm,
    ScreenshotForm,
    ScreenshotListSearchForm,
    ScreenshotSelectForm,
    ScreenshotSelectSearchForm,
    SearchForm,
)
from weblate.screenshots.models import Screenshot
from weblate.screenshots.ocr import ensure_ocr
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Unit
from weblate.trans.util import redirect_next
from weblate.utils import messages
from weblate.utils.search import parse_query
from weblate.utils.validators import PIL_FORMATS
from weblate.utils.views import PathViewMixin

if TYPE_CHECKING:
    from django.http import HttpResponse

    from weblate.auth.models import AuthenticatedHttpRequest


def add_sources(request: AuthenticatedHttpRequest, obj) -> dict[str, int | bool]:
    sources = request.POST.getlist("source")
    if not sources:
        return {"status": False, "added": 0, "skipped": 0, "invalid": 0}

    source_ids: list[int] = []
    seen: set[int] = set()
    skipped = 0
    invalid = 0
    for source in sources:
        try:
            source_id = int(source)
        except ValueError:
            invalid += 1
            continue
        if source_id in seen:
            skipped += 1
            continue
        seen.add(source_id)
        source_ids.append(source_id)

    existing = set(obj.units.filter(pk__in=source_ids).values_list("pk", flat=True))
    units = obj.translation.unit_set.in_bulk(source_ids)
    units_to_add: list[Unit] = []
    for source_id in source_ids:
        unit = units.get(source_id)
        if unit is None:
            invalid += 1
            continue
        if source_id in existing:
            skipped += 1
            continue
        units_to_add.append(unit)
        existing.add(source_id)

    obj.add_units(units_to_add, user=request.user)
    added = len(units_to_add)

    return {
        "status": added > 0,
        "added": added,
        "skipped": skipped,
        "invalid": invalid,
    }


async def add_sources_async(
    request: AuthenticatedHttpRequest, obj
) -> dict[str, int | bool]:
    sources = request.POST.getlist("source")
    if not sources:
        return {"status": False, "added": 0, "skipped": 0, "invalid": 0}

    source_ids: list[int] = []
    seen: set[int] = set()
    skipped = 0
    invalid = 0
    for source in sources:
        try:
            source_id = int(source)
        except ValueError:
            invalid += 1
            continue
        if source_id in seen:
            skipped += 1
            continue
        seen.add(source_id)
        source_ids.append(source_id)

    existing = {
        pk
        async for pk in obj.units.filter(pk__in=source_ids).values_list("pk", flat=True)
    }
    units = await obj.translation.unit_set.ain_bulk(source_ids)
    units_to_add: list[Unit] = []
    for source_id in source_ids:
        unit = units.get(source_id)
        if unit is None:
            invalid += 1
            continue
        if source_id in existing:
            skipped += 1
            continue
        units_to_add.append(unit)
        existing.add(source_id)

    await obj.add_units_async(units_to_add, user=request.user)
    added = len(units_to_add)

    return {
        "status": added > 0,
        "added": added,
        "skipped": skipped,
        "invalid": invalid,
    }


def try_add_source(request: AuthenticatedHttpRequest, obj) -> bool:
    return bool(add_sources(request, obj)["status"])


class ScreenshotList(PathViewMixin, ListView):  # type: ignore[misc]
    paginate_by = 48
    model = Screenshot
    supported_path_types = (Component,)
    _add_form = None

    sort_ordering: ClassVar[dict[str, tuple[str, ...]]] = {
        "name": ("name", "pk"),
        "-name": ("-name", "pk"),
        "-timestamp": ("-timestamp", "name", "pk"),
        "timestamp": ("timestamp", "name", "pk"),
        "language": ("translation__language__name", "name", "pk"),
        "-language": ("-translation__language__name", "name", "pk"),
        "-strings": ("-strings_count", "name", "pk"),
        "strings": ("strings_count", "name", "pk"),
    }
    search_preset_queries: ClassVar[tuple[str, ...]] = (
        "",
        "has:string",
        "NOT has:string",
        "has:repository",
        "has:repository AND NOT has:string",
    )

    def get_search_presets(self) -> list[dict[str, str]]:
        labels = {
            "": gettext("All screenshots"),
            "has:string": gettext("Assigned screenshots"),
            "NOT has:string": gettext("Unassigned screenshots"),
            "has:repository": gettext("Repository screenshots"),
            "has:repository AND NOT has:string": gettext(
                "Unassigned repository screenshots"
            ),
        }
        sort_by = ""
        if self.search_form.is_valid():
            sort_by = self.search_form.cleaned_data["sort_by"]

        result = []
        for query in self.search_preset_queries:
            params = []
            if query:
                params.append(("q", query))
            if sort_by and sort_by != "name":
                params.append(("sort_by", sort_by))
            result.append(
                {
                    "label": labels[query],
                    "query": query,
                    "query_string": urlencode(params),
                }
            )
        return result

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        data = self.request.GET.copy()
        if "q" not in data and data.get("assigned") == "0":
            data["q"] = "NOT has:string"
        self.search_form = ScreenshotListSearchForm(data=data)

    def get_queryset(self):
        result = (
            Screenshot.objects.filter(translation__component=self.path_object)
            .prefetch_related(
                "translation__component__category",
                "translation__component__project",
                "translation__language",
            )
            .annotate(strings_count=Count("units", distinct=True))
            .order()
        )
        if self.search_form.is_valid():
            if query := self.search_form.cleaned_data["q"]:
                filters, annotations = parse_query(
                    query,
                    parser="screenshot",
                    project=self.path_object.project,
                    component=self.path_object,
                )
                result = result.annotate(**annotations).filter(filters).distinct()
            sort_by = self.search_form.cleaned_data["sort_by"]
        else:
            sort_by = "name"
        return result.order_by(*self.sort_ordering[sort_by])

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = self.path_object
        result["add_form_active"] = self._add_form is not None
        result["search_form"] = self.search_form
        result["active_query"] = ""
        result["active_query_label"] = gettext("Filters")
        result["sort_query"] = "name"
        result["sort_name"] = self.search_form.sort_choices["name"]
        result["sort_choices"] = self.search_form.sort_choices
        result["sort_desc"] = False
        result["query_params"] = QueryDict()
        if self.search_form.is_valid():
            result["active_query"] = self.search_form.cleaned_data["q"]
            result["sort_query"] = self.search_form.cleaned_data["sort_by"]
            result["sort_name"] = self.search_form.sort_choices[
                result["sort_query"].removeprefix("-")
            ]
            result["sort_desc"] = result["sort_query"].startswith("-")
            result["query_params"] = QueryDict(self.search_form.urlencode())
        result["screenshot_search_presets"] = self.get_search_presets()
        for preset in result["screenshot_search_presets"]:
            if preset["query"] == result["active_query"]:
                result["active_query_label"] = preset["label"]
                break
        screenshots = Screenshot.objects.filter(translation__component=self.path_object)
        source_units = self.path_object.source_translation.unit_set
        source_strings_with_screenshots = (
            source_units.filter(screenshots__isnull=False).distinct().count()
        )
        source_strings_total = source_units.count()
        result["screenshot_summary"] = {
            "total": screenshots.count(),
            "unassigned": screenshots.filter(units__isnull=True).count(),
            "source_strings_with_screenshots": source_strings_with_screenshots,
            "source_strings_without_screenshots": (
                source_strings_total - source_strings_with_screenshots
            ),
            "source_translation": self.path_object.source_translation,
            "with_query": "has:screenshot",
            "without_query": "NOT has:screenshot",
            "assigned_query": urlencode({"q": "has:string"}),
            "unassigned_query": urlencode({"q": "NOT has:string"}),
        }
        if self._add_form is None:
            add_form = ScreenshotForm(self.path_object, self.request.user)
        else:
            add_form = self._add_form
        if add_form.permitted_translation_ids:
            result["add_form"] = add_form
        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        component = self.path_object
        self._add_form = ScreenshotForm(
            component, request.user, request.POST, request.FILES
        )
        if not self._add_form.permitted_translation_ids:
            raise PermissionDenied
        try:
            translation_id = int(request.POST["translation"])
        except (KeyError, ValueError):
            pass
        else:
            if (
                translation_id not in self._add_form.permitted_translation_ids
                and component.translation_set.filter(pk=translation_id).exists()
            ):
                raise PermissionDenied
        if self._add_form.is_valid():
            obj = Screenshot.objects.create(
                user=request.user, **self._add_form.cleaned_data
            )
            request.user.profile.increase_count("uploaded")
            obj.change_set.create(
                action=ActionEvents.SCREENSHOT_UPLOADED,
                user=request.user,
                target=obj.name,
            )

            try_add_source(request, obj)
            messages.success(
                request,
                gettext(
                    "Screenshot has been uploaded. "
                    "Search for source strings or find strings in the image."
                ),
            )
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect_next(next_url, obj)
        messages.error(
            request, gettext("Could not upload screenshot, please fix errors below.")
        )
        return self.get(request, **kwargs)


class ScreenshotBaseView(DetailView):
    model = Screenshot
    request: AuthenticatedHttpRequest

    def get_queryset(self):
        return Screenshot.objects.filter_access(self.request.user)

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        self.request.user.check_access_component(obj.translation.component)
        return obj


@method_decorator(cache_control(max_age=3600, private=True), name="dispatch")
class ScreenshotView(ScreenshotBaseView):
    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> FileResponse:  # type: ignore[override]
        obj = self.get_object()
        with Image.open(obj.image.open(), formats=PIL_FORMATS) as image:
            content_type = Image.MIME[cast("str", image.format)]
        return FileResponse(
            obj.image.open(),
            as_attachment=False,
            filename=os.path.basename(obj.image.name),
            content_type=content_type,
        )


class ScreenshotDetail(ScreenshotBaseView):
    _edit_form = None

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        translation = result["object"].translation
        if self.request.user.has_perm("screenshot.edit", translation):
            if self._edit_form is not None:
                result["edit_form"] = self._edit_form
            else:
                result["edit_form"] = ScreenshotEditForm(instance=result["object"])
        # Blank list for search results, this is populated later via JavaScript
        result["units"] = []
        result["search_query"] = ""
        return result

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> HttpResponse:
        obj = self.get_object()
        if request.user.has_perm("screenshot.edit", obj.translation):
            self._edit_form = ScreenshotEditForm(
                request.POST, request.FILES, instance=obj
            )
            if self._edit_form.is_valid():
                if request.FILES:
                    obj.user = request.user
                    request.user.profile.increase_count("uploaded")
                    obj.change_set.create(
                        action=ActionEvents.SCREENSHOT_UPLOADED,
                        user=request.user,
                        target=obj.name,
                    )
                self._edit_form.save()
            else:
                return self.get(request, *args, **kwargs)
        return redirect(obj)


@require_POST
@login_required
def delete_screenshot(request: AuthenticatedHttpRequest, pk):
    obj = get_object_or_404(Screenshot.objects.filter_access(request.user), pk=pk)
    component = obj.translation.component
    if not request.user.has_perm("screenshot.delete", obj.translation):
        raise PermissionDenied

    obj.delete()

    messages.success(request, gettext("Screenshot %s has been deleted.") % obj.name)

    return redirect_next(
        request.POST.get("next"),
        reverse("screenshots", kwargs={"path": component.get_url_path()}),
    )


def get_screenshot(request: AuthenticatedHttpRequest, pk):
    obj = get_object_or_404(Screenshot.objects.filter_access(request.user), pk=pk)
    if not request.user.has_perm("screenshot.edit", obj.translation):
        raise PermissionDenied
    return obj


async def aget_screenshot(request: AuthenticatedHttpRequest, pk):
    await request.user.aprepare_permissions()
    obj = await aget_object_or_404(
        Screenshot.objects.filter_access(request.user).select_related(
            "translation__component__project"
        ),
        pk=pk,
    )
    if not request.user.has_perm("screenshot.edit", obj.translation):
        raise PermissionDenied
    return obj


@require_POST
@login_required
async def remove_source(request: AuthenticatedHttpRequest, pk):
    obj = await aget_screenshot(request, pk)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    try:
        unit = await obj.translation.unit_set.aget(pk=int(request.POST["source"]))
    except (Unit.DoesNotExist, ValueError, KeyError):
        error = gettext("Invalid unit.")
        if is_ajax:
            return JsonResponse(
                data={"responseCode": 400, "status": False, "error": error},
                status=400,
            )
        messages.error(request, error)
        return redirect(obj)

    await obj.aremove_unit(unit, user=request.user)

    if is_ajax:
        return JsonResponse(data={"responseCode": 200, "status": True})

    messages.success(request, gettext("Source has been removed."))

    return redirect(obj)


def search_results(
    request: AuthenticatedHttpRequest,
    code,
    obj,
    units=None,
    *,
    error: str | None = None,
    result_kind: str = "search",
    task_url: str | None = None,
):
    if units is None:
        units = []
        count = 0
    else:
        units = (
            units.exclude(id__in=obj.units.values_list("id", flat=True))
            .prefetch_full()
            .count_screenshots()
        )
        count = len(units)

    data = {
        "responseCode": code,
        "count": count,
        "summary": ngettext(
            "%(count)s matching source string found.",
            "%(count)s matching source strings found.",
            count,
        )
        % {"count": count},
        "empty": gettext("No new matching source strings found."),
        "results": render_to_string(
            "screenshots/screenshot_sources_search.html",
            {
                "object": obj,
                "units": units,
                "user": request.user,
                "search_query": "",
                "result_kind": result_kind,
            },
        ),
    }
    if task_url is not None:
        data.update(pending=True, task_url=task_url)
    if error is not None:
        data["error"] = error
    return JsonResponse(data=data)


@login_required
@require_POST
def search_source(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    translation = obj.translation

    form = SearchForm(request.POST)
    if not form.is_valid():
        return search_results(request, 400, obj)
    filters, annotations = parse_query(
        form.cleaned_data["q"], project=translation.component.project
    )
    return search_results(
        request,
        200,
        obj,
        translation.unit_set.annotate(**annotations).filter(filters),
    )


@login_required
@require_POST
def ocr_search(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    cache = ensure_ocr(obj.pk, retry=request.POST.get("retry") == "1")
    if cache.error:
        error = (
            gettext(
                "Text recognition data could not be downloaded. Please try again later."
            )
            if cache.error == "download"
            else gettext("Could not find strings in the image. Please try again.")
        )
        return search_results(request, 503, obj, error=error, result_kind="ocr")
    if cache.data is None:
        return search_results(
            request,
            200,
            obj,
            result_kind="ocr",
            task_url=reverse("api:task-detail", kwargs={"pk": cache.task_id}),
        )

    sources = tuple(set(obj.translation.unit_set.values_list("source", flat=True)))
    matches = {
        match
        for result in cache.data["passes"]
        for line in result["lines"]
        for part in (line["text"], *line["text"].split("|"), *line["text"].split())
        for match in difflib.get_close_matches(part, sources, cutoff=0.9)
    }
    return search_results(
        request,
        200,
        obj,
        obj.translation.unit_set.filter(source__in=matches),
        result_kind="ocr",
    )


@login_required
@require_POST
async def add_source(request: AuthenticatedHttpRequest, pk):
    obj = await aget_screenshot(request, pk)
    return JsonResponse(
        data={"responseCode": 200, **await add_sources_async(request, obj)}
    )


@login_required
def get_sources(request: AuthenticatedHttpRequest, pk):
    obj = get_screenshot(request, pk)
    return render(
        request,
        "screenshots/screenshot_sources_body.html",
        {"object": obj, "search_query": ""},
    )


@login_required
@require_http_methods(["GET", "POST"])
def select_screenshot(request: AuthenticatedHttpRequest, unit_id: int) -> HttpResponse:
    unit = get_object_or_404(
        Unit.objects.filter_access(request.user).select_related(
            "translation__component__project"
        ),
        pk=unit_id,
    )
    component = unit.translation.component
    request.user.check_access_component(component)
    if not request.user.has_perm("screenshot.edit", unit.translation):
        raise PermissionDenied
    source_unit = unit.source_unit
    screenshots = (
        Screenshot.objects.filter_access(request.user)
        .filter(translation_id__in={unit.translation_id, source_unit.translation_id})
        .select_related("translation__component__project")
    )
    if request.method == "POST":
        form = ScreenshotSelectForm(screenshots, request.POST)
        if not form.is_valid():
            return JsonResponse(
                {"error": gettext("Select a valid screenshot.")}, status=400
            )
        screenshot = form.cleaned_data["screenshot"]
        # Serialize submissions so retries do not duplicate change events.
        with transaction.atomic():
            screenshot = (
                Screenshot.objects.select_for_update()
                .select_related("translation__component__project")
                .get(pk=screenshot.pk)
            )
            if screenshot.translation_id not in {
                unit.translation_id,
                source_unit.translation_id,
            } or not request.user.has_perm("screenshot.edit", screenshot.translation):
                raise PermissionDenied
            target = (
                source_unit
                if screenshot.translation_id == source_unit.translation_id
                else unit
            )
            if not screenshot.units.filter(pk=target.pk).exists():
                screenshot.add_unit(target, user=request.user)
        return JsonResponse({"success": True})

    search_form = ScreenshotSelectSearchForm(
        request.GET, auto_id="screenshot-picker-%s"
    )
    permitted_translation_ids = {
        translation.pk
        for translation in (unit.translation, source_unit.translation)
        if request.user.has_perm("screenshot.edit", translation)
    }
    screenshots = screenshots.filter(
        translation_id__in=permitted_translation_ids
    ).exclude(units__in={unit.pk, source_unit.pk})
    if search_form.is_valid():
        if query := search_form.cleaned_data["q"]:
            filters, annotations = parse_query(
                query,
                parser="screenshot",
                project=component.project,
                component=component,
            )
            screenshots = screenshots.annotate(**annotations).filter(filters).distinct()
    else:
        screenshots = screenshots.none()
    page = Paginator(
        screenshots.select_related("translation__language").order_by("name", "pk"), 48
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "screenshots/screenshot_select.html",
        {"search_form": search_form, "page_obj": page},
    )
