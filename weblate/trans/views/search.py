# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.http import QueryDict
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext, ngettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.trans.bulk import BULK_EDIT_PREVIEW_LIMIT, bulk_perform
from weblate.trans.forms import (
    BulkEditForm,
    SearchForm,
)
from weblate.trans.models import Category, Component, Project, Translation
from weblate.trans.models.unit import fill_in_source_translation
from weblate.trans.util import redirect_next, render
from weblate.utils import messages
from weblate.utils.bulk_regex import regex_session
from weblate.utils.ratelimit import check_rate_limit
from weblate.utils.stats import CategoryLanguage, ProjectLanguage, WorkspaceLanguage
from weblate.utils.views import (
    get_paginator,
    import_message,
    optional_form,
    parse_path_units,
    show_form_errors,
)
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.trans.bulk import BulkUnitEdit


SEARCH_SUMMARY_MAX_STRINGS = 1_000
BULK_EDIT_TYPES = (
    Translation,
    Component,
    Project,
    ProjectLanguage,
    Category,
    CategoryLanguage,
    Workspace,
)


def browse(request: AuthenticatedHttpRequest, path):
    """Redirect legacy string lists to search, preserving their pagination."""
    params = request.GET.copy()
    if "offset" in params:
        if "page" not in params:
            try:
                params["page"] = str(max(1, int(params.get("offset", "1"))))
            except ValueError:
                params["page"] = "1"
            params["limit"] = "20"
        del params["offset"]
    url = reverse("search", kwargs={"path": path})
    if params:
        url = f"{url}?{params.urlencode()}"
    return redirect(url, permanent=True)


@login_required
@require_POST
def search_replace(request: AuthenticatedHttpRequest, path):
    """Accept the legacy replacement URL through the unified bulk-edit flow."""
    data = request.POST.copy()
    data.setdefault("state", "-1")
    data.setdefault("preview", "1")
    if not data.get("q"):
        data["q"] = "NOT id:0"
    return bulk_edit(request, path, data=data)


@never_cache
def search(request: AuthenticatedHttpRequest, path=None):
    """Perform site-wide search on units."""
    is_ratelimited = not check_rate_limit("search", request)
    obj, unit_set, context = parse_path_units(
        request,
        path,
        (
            Component,
            Project,
            ProjectLanguage,
            Translation,
            Category,
            CategoryLanguage,
            Workspace,
            WorkspaceLanguage,
            Language,
            None,
        ),
    )

    search_form = SearchForm(request=request, data=request.GET, obj=obj)
    context["search_form"] = search_form
    context["has_editor"] = isinstance(
        obj, (Translation, ProjectLanguage, CategoryLanguage, WorkspaceLanguage)
    )

    if (
        not is_ratelimited
        and (obj is not None or request.GET)
        and search_form.is_valid()
    ):
        # This is ugly way to hide query builder when showing results
        search_form = SearchForm(
            request=request, data=request.GET, show_builder=False, obj=obj
        )
        search_form.is_valid()
        search_units = unit_set.prefetch_bulk().search(
            search_form.cleaned_data.get("q", ""),
            project=context.get("project"),
            user=request.user,
        )
        ordered_units = search_units.order_by_request(search_form.cleaned_data, obj)
        units = get_paginator(request, ordered_units)
        total_strings = units.paginator.count
        total_words = None
        if total_strings <= SEARCH_SUMMARY_MAX_STRINGS:
            total_words = search_units.aggregate(total_words=Sum("num_words"))[
                "total_words"
            ]

        # Make sure source translation is available
        fill_in_source_translation(units)
        # Rebuild context from scratch here to get new form
        context.update(
            {
                "search_form": search_form,
                "show_results": True,
                "page_obj": units,
                "path_object": obj,
                "title": gettext("Search for %s") % search_form.cleaned_data["q"]
                if search_form.cleaned_data["q"]
                else gettext("All strings"),
                "query_params": QueryDict(search_form.urlencode()),
                "search_query": search_form.cleaned_data["q"],
                "sort_query": search_form.sort_query,
                "total_strings": total_strings,
                "total_words": total_words,
            }
        )
        if isinstance(
            obj, (Translation, ProjectLanguage, CategoryLanguage, WorkspaceLanguage)
        ):
            context["translate_url"] = (
                f"{reverse('translate', kwargs={'path': obj.get_url_path()})}"
                f"?{search_form.urlencode()}"
            )
        if isinstance(obj, BULK_EDIT_TYPES):
            bulk_state_form = optional_form(
                BulkEditForm,
                request.user,
                "unit.bulk_edit",
                obj,
                user=request.user,
                obj=obj,
                project=context.get("project"),
                selection=True,
            )
            if bulk_state_form is not None:
                context["bulk_state_form"] = bulk_state_form
                # Render selection checkboxes in the listing
                context["selection_template"] = "snippets/bulk-edit-selection.html"
                context["selection_header_template"] = (
                    "snippets/bulk-edit-selection-header.html"
                )
    elif is_ratelimited:
        messages.error(
            request, gettext("Too many search queries, please try again later.")
        )
    elif request.GET:
        messages.error(request, gettext("Invalid search query!"))
        show_form_errors(request, search_form)

    return render(request, "search.html", context)


@login_required
@require_POST
@never_cache
@regex_session()
def bulk_edit(
    request: AuthenticatedHttpRequest, path, *, data: QueryDict | None = None
):
    obj, unit_set, context = parse_path_units(request, path, BULK_EDIT_TYPES)

    if isinstance(obj, Workspace):
        unit_set = unit_set.filter_editable_scope(request.user)
        can_edit = unit_set.exists()
    else:
        can_edit = request.user.has_perm("unit.edit", obj)
    if not request.user.has_perm("unit.bulk_edit", obj) or not can_edit:
        raise PermissionDenied

    data = request.POST.copy() if data is None else data
    confirmation = None
    if token := data.get("bulk_confirmation"):
        try:
            confirmation = signing.loads(
                token,
                salt=f"bulk-edit:{request.user.pk}:{request.path}",
                max_age=3600,
            )
            data = QueryDict(mutable=True)
            for key, values in confirmation["data"].items():
                data.setlist(key, values)
        except (signing.BadSignature, KeyError, TypeError):
            messages.error(
                request,
                gettext(
                    "The preview has expired or is invalid. Preview the changes again."
                ),
            )
            return redirect(obj)

    form = BulkEditForm(
        request.user,
        obj,
        data,
        project=context.get("project"),
        selection=True,
    )
    next_url = data.get("next")
    if not form.is_valid():
        messages.error(request, gettext("Could not process form!"))
        show_form_errors(request, form)
        return redirect_next(next_url, obj)
    options = {
        "query": form.get_query(),
        "target_state": form.cleaned_data["state"],
        **{
            name: form.cleaned_data[name]
            for name in (
                "search",
                "replacement",
                "search_type",
                "add_flags",
                "remove_flags",
                "add_translation_flags",
                "remove_translation_flags",
                "add_labels",
                "remove_labels",
            )
        },
        "project": context.get("project"),
        "components": context["components"],
    }
    if confirmation is not None and request.POST.get("apply_all") != "1":
        try:
            selected = {int(pk) for pk in request.POST.getlist("preview_units")}
        except ValueError:
            raise PermissionDenied from None
        if not selected <= set(confirmation["candidates"]):
            raise PermissionDenied
        unit_set = unit_set.filter(pk__in=selected)
    preview: list[BulkUnitEdit] | None = (
        [] if confirmation is None and form.cleaned_data["preview"] else None
    )
    try:
        updated = bulk_perform(request.user, unit_set, preview=preview, **options)
    except ValidationError as error:
        messages.error(
            request, gettext("Bulk edit failed: %s") % "; ".join(error.messages)
        )
        return redirect_next(next_url, obj)

    if preview is not None:
        return render_bulk_preview(request, obj, data, form, context, preview, updated)

    import_message(
        request,
        updated,
        gettext("Bulk edit completed, no strings were updated."),
        ngettext(
            "Bulk edit completed, %d string was updated.",
            "Bulk edit completed, %d strings were updated.",
            updated,
        ),
    )

    return redirect_next(next_url, obj)


def render_bulk_preview(
    request: AuthenticatedHttpRequest,
    obj,
    data: QueryDict,
    form: BulkEditForm,
    context,
    preview: list[BulkUnitEdit],
    total: int,
):
    """Render bounded candidates while retaining the original operation scope."""
    preview = preview[:BULK_EDIT_PREVIEW_LIMIT]
    preview_data = data.copy()
    preview_data["q"] = form.get_query()
    preview_data.pop("units", None)
    edit_form = BulkEditForm(
        request.user, obj, preview_data, project=context.get("project")
    )
    context.update(
        {
            "matching": preview,
            "total": total,
            "limited": total > BULK_EDIT_PREVIEW_LIMIT,
            "form": edit_form,
            "next": data.get("next", ""),
            "confirmation": signing.dumps(
                {
                    "data": {
                        key: values
                        for key, values in data.lists()
                        if key != "csrfmiddlewaretoken"
                    },
                    "candidates": [edit.unit.pk for edit in preview],
                },
                salt=f"bulk-edit:{request.user.pk}:{request.path}",
                compress=True,
            ),
        }
    )
    return render(request, "bulk-edit.html", context)
