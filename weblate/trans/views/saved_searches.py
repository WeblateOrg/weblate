# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import aget_object_or_404, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.trans.forms import SavedSearchForm
from weblate.trans.models import Project, SavedSearch
from weblate.trans.util import redirect_next, render
from weblate.utils.views import aparse_path, parse_path

if TYPE_CHECKING:
    from django.http import HttpResponse

    from weblate.auth.models import AuthenticatedHttpRequest


USER_SEARCHES_URL = reverse_lazy("profile", fragment="searches")


def get_initial(request: AuthenticatedHttpRequest) -> dict[str, str]:
    """Prefill the query when coming from the search form."""
    if query := request.GET.get("q"):
        return {"query": query}
    return {}


@login_required
@never_cache
def user_saved_search_edit(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    saved_search = get_object_or_404(
        SavedSearch, pk=pk, user=request.user, project__isnull=True
    )

    if request.method == "POST":
        form = SavedSearchForm(
            user=request.user, data=request.POST, instance=saved_search
        )
        if form.is_valid():
            form.save()
            return redirect(USER_SEARCHES_URL)
    else:
        form = SavedSearchForm(user=request.user, instance=saved_search)

    return render(
        request,
        "accounts/saved-search-edit.html",
        {"form": form},
    )


@login_required
@never_cache
@require_POST
async def user_saved_search_delete(
    request: AuthenticatedHttpRequest, pk: int
) -> HttpResponse:
    saved_search = await aget_object_or_404(
        SavedSearch, pk=pk, user=request.user, project__isnull=True
    )

    await saved_search.adelete()

    return redirect(USER_SEARCHES_URL)


@login_required
@never_cache
def project_saved_searches(
    request: AuthenticatedHttpRequest, project: str
) -> HttpResponse:
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

    if request.method == "POST":
        form = SavedSearchForm(user=request.user, project=obj, data=request.POST)
        if form.is_valid():
            form.save()
            return redirect("project-saved-searches", project=project)
    else:
        form = SavedSearchForm(
            user=request.user, project=obj, initial=get_initial(request)
        )

    return render(
        request,
        "project-saved-searches.html",
        {
            "object": obj,
            "project": obj,
            "form": form,
            "saved_searches": obj.savedsearch_set.order(),
        },
    )


@login_required
@never_cache
def project_saved_search_edit(
    request: AuthenticatedHttpRequest, project: str, pk: int
) -> HttpResponse:
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

    saved_search = get_object_or_404(SavedSearch, pk=pk, project=obj)

    if request.method == "POST":
        form = SavedSearchForm(
            user=request.user, project=obj, data=request.POST, instance=saved_search
        )
        if form.is_valid():
            form.save()
            return redirect("project-saved-searches", project=project)
    else:
        form = SavedSearchForm(user=request.user, project=obj, instance=saved_search)

    return render(
        request,
        "project-saved-search-edit.html",
        {"object": obj, "project": obj, "form": form},
    )


@login_required
@never_cache
@require_POST
async def project_saved_search_delete(
    request: AuthenticatedHttpRequest, project: str, pk: int
) -> HttpResponse:
    obj = await aparse_path(request, [project], (Project,))

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

    saved_search = await aget_object_or_404(SavedSearch, pk=pk, project=obj)

    await saved_search.adelete()

    return redirect("project-saved-searches", project=project)


@login_required
@never_cache
def saved_search_create(request: AuthenticatedHttpRequest) -> HttpResponse:
    """
    Save the current search from the search form.

    Offers the project scope only to users who can manage the project.
    """
    project: Project | None = None
    project_slug = request.POST.get("project") or request.GET.get("project")
    if project_slug:
        candidate = parse_path(request, [project_slug], (Project,))
        if request.user.has_perm("project.edit", candidate):
            project = candidate
    next_url = request.POST.get("next") or request.GET.get("next")

    if request.method == "POST":
        form = SavedSearchForm(
            user=request.user,
            project=project,
            scope_choice=True,
            data=request.POST,
        )
        if form.is_valid():
            form.save()
            return redirect_next(next_url, USER_SEARCHES_URL)
    else:
        form = SavedSearchForm(
            user=request.user,
            project=project,
            scope_choice=True,
            initial=get_initial(request),
        )

    return render(
        request,
        "saved-search-create.html",
        {
            "form": form,
            "project": project,
            "next_url": next_url,
        },
    )
