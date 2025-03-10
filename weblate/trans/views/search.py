# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.utils.translation import gettext, ngettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.bulk import bulk_perform
from weblate.trans.forms import (
    BulkEditForm,
    ReplaceConfirmForm,
    ReplaceForm,
    SearchForm,
)
from weblate.trans.models import Category, Component, Project, Translation, Unit
from weblate.trans.util import render
from weblate.utils import messages
from weblate.utils.ratelimit import check_rate_limit
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import (
    get_paginator,
    get_sort_name,
    import_message,
    parse_path_units,
    show_form_errors,
)

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@login_required
@require_POST
def search_replace(request: AuthenticatedHttpRequest, path):
    obj, unit_set, context = parse_path_units(
        request,
        path,
        (Translation, Component, Project, ProjectLanguage, Category, CategoryLanguage),
    )

    if not request.user.has_perm("unit.edit", obj):
        raise PermissionDenied

    form = ReplaceForm(obj=obj, data=request.POST)

    if not form.is_valid():
        messages.error(request, gettext("Could not process form!"))
        show_form_errors(request, form)
        return redirect(obj)

    search_text = form.cleaned_data["search"]
    replacement = form.cleaned_data["replacement"]
    query = form.cleaned_data.get("q")

    matching = unit_set.filter(target__contains=search_text)
    if query:
        matching = matching.search(query)

    updated = 0

    matching_ids = list(matching.order_by("id").values_list("id", flat=True)[:251])

    if matching_ids:
        if len(matching_ids) == 251:
            matching_ids = matching_ids[:250]
            limited = True
        else:
            limited = False

        matching = Unit.objects.filter(id__in=matching_ids).prefetch()

        confirm = ReplaceConfirmForm(matching, request.POST)

        if not confirm.is_valid():
            for unit in matching:
                unit.replacement = unit.target.replace(search_text, replacement)
            context.update(
                {
                    "matching": matching,
                    "search_query": search_text,
                    "replacement": replacement,
                    "form": form,
                    "limited": limited,
                    "confirm": ReplaceConfirmForm(matching),
                }
            )
            return render(request, "replace.html", context)

        matching = confirm.cleaned_data["units"]

        with transaction.atomic():
            for unit in matching.select_for_update():
                if not request.user.has_perm("unit.edit", unit):
                    continue
                unit.translate(
                    request.user,
                    unit.target.replace(search_text, replacement),
                    unit.state,
                    change_action=ActionEvents.REPLACE,
                )
                updated += 1

    import_message(
        request,
        updated,
        gettext("Search and replace completed, no strings were updated."),
        ngettext(
            "Search and replace completed, %d string was updated.",
            "Search and replace completed, %d strings were updated.",
            updated,
        ),
    )

    return redirect(obj)


@never_cache
def search(request: AuthenticatedHttpRequest, path=None):
    """Perform site-wide search on units."""
    is_ratelimited = not check_rate_limit("search", request)
    search_form = SearchForm(user=request.user, data=request.GET)
    sort = get_sort_name(request)
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
            Language,
            None,
        ),
    )

    context["search_form"] = search_form
    context["back_url"] = obj.get_absolute_url() if obj is not None else None

    if not is_ratelimited and request.GET and search_form.is_valid():
        # This is ugly way to hide query builder when showing results
        search_form = SearchForm(
            user=request.user, data=request.GET, show_builder=False
        )
        search_form.is_valid()
        units = unit_set.prefetch_bulk().search(
            search_form.cleaned_data.get("q", ""), project=context.get("project")
        )

        # Count total strings and sum total words from the search results
        aggregation = units.aggregate(
            total_strings=Count("id"), total_words=Sum("num_words")
        )
        # Get the total strings and total words from the aggregation
        total_strings = aggregation["total_strings"]
        total_words = aggregation["total_words"]

        units = get_paginator(
            request, units.order_by_request(search_form.cleaned_data, obj)
        )
        # Rebuild context from scratch here to get new form
        context.update(
            {
                "search_form": search_form,
                "show_results": True,
                "page_obj": units,
                "path_object": obj,
                "title": gettext("Search for %s") % (search_form.cleaned_data["q"]),
                "query_string": search_form.urlencode(),
                "search_url": search_form.urlencode(),
                "search_query": search_form.cleaned_data["q"],
                "search_items": search_form.items(),
                "sort_name": sort["name"],
                "sort_query": sort["query"],
                "total_strings": total_strings,
                "total_words": total_words,
            }
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
def bulk_edit(request: AuthenticatedHttpRequest, path):
    obj, unit_set, context = parse_path_units(
        request,
        path,
        (Translation, Component, Project, ProjectLanguage, Category, CategoryLanguage),
    )

    if not request.user.has_perm("translation.auto", obj) or not request.user.has_perm(
        "unit.edit", obj
    ):
        raise PermissionDenied

    form = BulkEditForm(request.user, obj, request.POST, project=context["project"])

    if not form.is_valid():
        messages.error(request, gettext("Could not process form!"))
        show_form_errors(request, form)
        return redirect(obj)

    updated = bulk_perform(
        request.user,
        unit_set,
        query=form.cleaned_data["q"],
        target_state=form.cleaned_data["state"],
        add_flags=form.cleaned_data["add_flags"],
        remove_flags=form.cleaned_data["remove_flags"],
        add_labels=form.cleaned_data["add_labels"],
        remove_labels=form.cleaned_data["remove_labels"],
        project=context["project"],
        components=context["components"],
    )

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

    return redirect(obj)
