# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache

from weblate.trans.forms import AutoForm, BulkEditForm, SearchForm
from weblate.trans.models.change import Change
from weblate.trans.models.project import prefetch_project_flags
from weblate.utils import messages
from weblate.utils.views import get_paginator
from weblate.workspaces.forms import WorkspaceSettingsForm
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
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

    # ruff: ignore[import-outside-top-level]
    from weblate.billing.forms import (
        BillingMergeForm,
        HostingForm,
    )

    return {
        "billing": billing,
        "hosting_form": HostingForm(),
        "merge_form": BillingMergeForm(),
    }


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


@never_cache
def detail(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    workspace = get_object_or_404(Workspace, pk=pk)
    projects = request.user.allowed_projects.filter(workspace=workspace).order()
    billing = get_workspace_billing(workspace)
    user_can_view_billing = billing is not None and request.user.has_perm(
        "meta:billing.view", billing
    )
    can_edit_workspace = request.user.has_perm("workspace.edit", workspace)
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

    active_tab = "projects"
    if request.method == "POST":
        if not can_edit_workspace:
            msg = "Access denied"
            raise Http404(msg)
        workspace.acting_user = request.user
        settings_form = WorkspaceSettingsForm(request.POST, instance=workspace)
        if settings_form.is_valid():
            settings_form.save()
            messages.success(request, gettext("Settings saved"))
            return redirect(f"{workspace.get_absolute_url()}#settings")
        active_tab = "settings"
        messages.error(
            request, gettext("Invalid settings. Please check the form for errors.")
        )
    else:
        settings_form = WorkspaceSettingsForm(instance=workspace)

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
            "bulk_state_form": BulkEditForm(request.user, workspace)
            if request.user.has_perm("unit.bulk_edit", workspace)
            and request.user.has_perm("unit.edit", workspace)
            else None,
            "create_project_url": get_create_project_url(request, workspace, billing),
            "last_changes": Change.objects.last_changes(
                request.user, workspace=workspace
            ).recent(),
            "can_edit_workspace": can_edit_workspace,
            "can_manage_access": can_manage_access,
            "workspace_teams": workspace.defined_groups.annotate(Count("user"))
            .order()
            .prefetch_related("roles"),
            "settings_form": settings_form,
            "active_tab": active_tab,
            **get_billing_context(request, billing),
        },
    )
