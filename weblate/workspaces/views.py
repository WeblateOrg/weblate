# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, ProtectedError, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from weblate.trans.forms import AutoForm, BulkEditForm, ReplaceForm, SearchForm
from weblate.trans.models.change import Change
from weblate.trans.models.project import Project, prefetch_project_flags
from weblate.trans.models.translation import Translation
from weblate.trans.models.unit import Unit
from weblate.trans.views.files import can_download_workspace
from weblate.trans.views.reports import get_reports_context
from weblate.utils import messages
from weblate.utils.stats import prefetch_stats
from weblate.utils.views import get_paginator, show_form_errors
from weblate.workspaces.forms import WorkspaceDeleteForm, WorkspaceSearchForm
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from django.db.models import QuerySet

    from weblate.auth.models import AuthenticatedHttpRequest
    from weblate.billing.models import Billing


def get_workspace_billing(workspace: Workspace) -> Billing | None:
    if "weblate.billing" not in settings.INSTALLED_APPS:
        return None

    with suppress(AttributeError, ObjectDoesNotExist):
        return workspace.billing

    return None


def get_billing_context(
    request: AuthenticatedHttpRequest, billing: Billing | None
) -> dict:
    if billing is None or not request.user.has_perm("meta:billing.view", billing):
        return {}

    return {"billing": billing}


def billing_allows_project_creation(billing: Billing) -> bool:
    if not billing.in_limits:
        return False
    if billing.state == billing.STATE_ACTIVE and not billing.paid:
        return False
    if billing.state not in billing.ACTIVE_STATES:
        return False

    limit = billing.plan.display_limit_projects
    return limit == 0 or billing.get_projects_queryset().count() < limit


def get_create_project_url(
    request: AuthenticatedHttpRequest, workspace: Workspace, billing: Billing | None
) -> str | None:
    if not request.user.has_perm("workspace.add_project", workspace):
        return None

    if billing is not None and not billing_allows_project_creation(billing):
        return None

    return f"{reverse('create-project')}?{urlencode({'workspace': workspace.pk})}"


class WorkspaceListBase(ListView):
    model = Workspace
    request: AuthenticatedHttpRequest

    def include_billing(self) -> bool:
        return False

    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:  # type: ignore[override]
        super().setup(request, *args, **kwargs)
        self.search_form = WorkspaceSearchForm(request.GET)

    def get_base_queryset(self) -> QuerySet[Workspace]:
        return Workspace.objects.all()

    def get_queryset(self) -> QuerySet[Workspace]:
        review_projects = Project.objects.filter(workspace_id=OuterRef("pk")).filter(
            Q(source_review=True) | Q(translation_review=True)
        )
        queryset = (
            self.get_base_queryset()
            .annotate(
                Count("projects"),
                stats_has_review=Exists(review_projects),
            )
            .prefetch_related(
                Prefetch(
                    "projects",
                    queryset=Project.objects.only("id", "slug", "workspace"),
                )
            )
            .order_by("name")
        )
        if self.search_form.is_valid() and (
            query := self.search_form.cleaned_data["q"].strip()
        ):
            filters = Q(name__icontains=query)
            if self.include_billing():
                filters |= Q(billing__customer_name__icontains=query)
            queryset = queryset.filter(filters)
        if self.include_billing():
            queryset = queryset.select_related("billing")
        return queryset

    @staticmethod
    def prepare_workspace_stats(workspaces: Iterable[Workspace]) -> None:
        """Batch language counts needed to initialize uncached workspace stats."""
        missing = [
            workspace for workspace in workspaces if not workspace.stats.has_cached_data
        ]
        if not missing:
            return

        language_ids: dict[UUID, set[int]] = {
            workspace.pk: set() for workspace in missing
        }
        workspace_ids = language_ids.keys()
        owned_languages = Translation.objects.filter(
            component__project__workspace_id__in=workspace_ids
        ).values_list("component__project__workspace_id", "language_id")
        shared_languages = Translation.objects.filter(
            component__links__workspace_id__in=workspace_ids
        ).values_list("component__links__workspace_id", "language_id")
        for workspace_id, language_id in owned_languages.union(shared_languages):
            language_ids[workspace_id].add(language_id)
        for workspace in missing:
            workspace.stats_languages = len(language_ids[workspace.pk])

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        result = super().get_context_data(**kwargs)
        queryset = result["object_list"]
        sort_by = self.request.GET.get("sort_by")
        if sort_by and sort_by.lstrip("-") != "name":
            queryset = prefetch_stats(queryset)
            self.prepare_workspace_stats(queryset)
        workspaces = get_paginator(
            self.request,
            queryset,
            page_limit=50,
            stats=True,
            sort_by=sort_by,
        )
        self.prepare_workspace_stats(workspaces)
        result["object_list"] = workspaces
        result["page_obj"] = workspaces
        result["paginator"] = workspaces.paginator
        result["is_paginated"] = workspaces.paginator.num_pages > 1
        search_query = ""
        if self.search_form.is_valid():
            search_query = self.search_form.cleaned_data["q"].strip()
        search_items = (("q", search_query),) if search_query else ()
        result["billing_enabled"] = self.include_billing()
        result["workspace_creation_enabled"] = (
            "weblate.billing" not in settings.INSTALLED_APPS
        )
        result["can_add_workspace"] = self.request.user.has_perm("workspace.add")
        result["search_form"] = self.search_form
        result["search_query"] = search_query
        result["search_items"] = search_items
        result["query_string"] = urlencode(search_items)
        result["show_review_columns"] = (
            Project.objects.filter(workspace__in=queryset)
            .filter(Q(source_review=True) | Q(translation_review=True))
            .exists()
        )
        return result


@method_decorator(login_required, name="dispatch")
class WorkspaceListView(WorkspaceListBase):
    template_name = "workspaces.html"

    def get_base_queryset(self) -> QuerySet[Workspace]:
        return Workspace.objects.filter(
            pk__in=self.request.user.workspace_permissions.keys()
        )

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        result = super().get_context_data(**kwargs)
        result["title"] = gettext("My workspaces")
        return result


@never_cache
def detail(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    workspace = get_object_or_404(Workspace, pk=pk)
    projects = request.user.allowed_projects.filter(workspace=workspace).order()
    workspace_has_projects = workspace.projects.exists()
    billing = get_workspace_billing(workspace)
    user_can_view_billing = billing is not None and request.user.has_perm(
        "meta:billing.view", billing
    )
    can_edit_workspace = request.user.has_perm("workspace.edit", workspace)
    can_edit_units = (
        Unit.objects.filter(translation__component__project__workspace=workspace)
        .filter_access(request.user)
        .filter_editable_scope(request.user)
        .exists()
    )
    user_has_workspace_access = any(
        request.user.has_perm(permission, workspace)
        for permission in (
            "workspace.edit",
            "workspace.add_project",
            "workspace.edit_members",
        )
    )
    can_manage_access = request.user.has_perm("workspace.edit_members", workspace)
    if (
        not projects.exists()
        and not user_can_view_billing
        and not user_has_workspace_access
        and not request.user.has_perm("management.use")
    ):
        msg = "Access denied"
        raise Http404(msg)

    show_review_columns = projects.filter(
        Q(source_review=True) | Q(translation_review=True)
    ).exists()
    search_query = request.GET.copy()
    search_query.pop("sort_by", None)

    return render(
        request,
        "workspace.html",
        {
            "object": workspace,
            "workspace": workspace,
            "projects": prefetch_project_flags(
                get_paginator(
                    request,
                    projects,
                    stats=True,
                    sort_by=request.GET.get("sort_by"),
                )
            ),
            "title": workspace.name,
            "query_string": "",
            "show_review_columns": show_review_columns,
            "search_form": SearchForm(
                request=request,
                initial=SearchForm.get_initial(request),
                obj=workspace,
                query_data=search_query,
            ),
            "autoform": AutoForm(workspace, user=request.user)
            if request.user.has_perm("translation.auto", workspace)
            else None,
            "replace_form": ReplaceForm(workspace) if can_edit_units else None,
            "bulk_state_form": BulkEditForm(request.user, workspace)
            if request.user.has_perm("unit.bulk_edit", workspace) and can_edit_units
            else None,
            "create_project_url": get_create_project_url(request, workspace, billing),
            "delete_form": WorkspaceDeleteForm(workspace)
            if can_edit_workspace and not workspace_has_projects and billing is None
            else None,
            "last_changes": Change.objects.last_changes(
                request.user, workspace=workspace
            ).recent(),
            "can_edit_workspace": can_edit_workspace,
            "can_manage_access": can_manage_access,
            "can_download_workspace": can_download_workspace(request.user, workspace),
            "workspace_has_billing": billing is not None,
            "workspace_has_projects": workspace_has_projects,
            **(
                get_reports_context(request, workspace)
                if request.user.is_authenticated
                else {}
            ),
            **get_billing_context(request, billing),
        },
    )


@never_cache
@login_required
@require_POST
@transaction.atomic
def remove(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    workspace = get_object_or_404(Workspace.objects.select_for_update(), pk=pk)
    if not request.user.has_perm("workspace.edit", workspace):
        msg = "Access denied"
        raise Http404(msg)

    if workspace.projects.exists():
        messages.error(
            request,
            gettext(
                "The workspace cannot be removed while it contains projects. "
                "Move or remove the projects first."
            ),
        )
        return redirect(f"{workspace.get_absolute_url()}#organize")

    if get_workspace_billing(workspace) is not None:
        messages.error(
            request,
            gettext("A workspace associated with billing cannot be removed."),
        )
        return redirect(f"{workspace.get_absolute_url()}#organize")

    form = WorkspaceDeleteForm(workspace, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect(f"{workspace.get_absolute_url()}#organize")

    try:
        workspace.delete()
    except ProtectedError:
        messages.error(
            request,
            gettext("The workspace cannot be removed because it is still being used."),
        )
        return redirect(f"{workspace.get_absolute_url()}#organize")

    messages.success(request, gettext("The workspace has been removed."))
    return redirect("home")


@never_cache
def access(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    workspace = get_object_or_404(Workspace, pk=pk)
    if not request.user.has_perm("workspace.edit_members", workspace):
        msg = "Access denied"
        raise Http404(msg)

    return render(
        request,
        "workspace-access.html",
        {
            "object": workspace,
            "workspace": workspace,
            "title": gettext("Access control"),
            "workspace_teams": workspace.defined_groups.annotate(Count("user"))
            .order()
            .prefetch_related("roles"),
        },
    )
