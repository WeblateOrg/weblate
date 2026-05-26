# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from weblate.trans.models.project import prefetch_project_flags
from weblate.utils.views import get_paginator
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

    from weblate.billing.forms import (  # noqa: PLC0415
        BillingMergeForm,
        BillingUserForm,
        HostingForm,
    )

    return {
        "billing": billing,
        "hosting_form": HostingForm(),
        "merge_form": BillingMergeForm(),
        "user_form": BillingUserForm(),
    }


def get_create_project_url(
    request: AuthenticatedHttpRequest, billing: Billing | None
) -> str | None:
    if billing is None:
        return None

    from weblate.billing.models import Billing  # noqa: PLC0415

    if not (
        Billing.objects.filter(pk=billing.pk)
        .for_user_within_limits(request.user)
        .exists()
    ):
        return None

    return f"{reverse('create-project')}?{urlencode({'billing': billing.pk})}"


@never_cache
def detail(request: AuthenticatedHttpRequest, pk) -> HttpResponse:
    workspace = get_object_or_404(Workspace, pk=pk)
    projects = request.user.allowed_projects.filter(workspace=workspace).order()
    billing = get_workspace_billing(workspace)
    user_can_view_billing = billing is not None and request.user.has_perm(
        "meta:billing.view", billing
    )
    if (
        not projects.exists()
        and not user_can_view_billing
        and not request.user.has_perm("management.use")
    ):
        msg = "Access denied"
        raise Http404(msg)

    show_review_columns = projects.filter(
        Q(source_review=True) | Q(translation_review=True)
    ).exists()

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
            "create_project_url": get_create_project_url(request, billing),
            **get_billing_context(request, billing),
        },
    )
