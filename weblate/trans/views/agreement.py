# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from weblate.trans.forms import ContributorAgreementForm
from weblate.trans.models import Category, Component, ContributorAgreement, Project
from weblate.trans.util import redirect_next
from weblate.utils.views import parse_path
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def get_agreement_owner_lookup(
    obj: Category | Component | Project | Workspace,
) -> dict[str, Category | Component | Project | Workspace]:
    if not isinstance(obj, Workspace):
        obj = obj.get_effective_setting_owner("agreement")
    if isinstance(obj, Workspace):
        return {"workspace": obj}
    if isinstance(obj, Project):
        return {"project": obj}
    if isinstance(obj, Category):
        return {"category": obj}
    return {"component": obj}


def get_agreement_text(obj: Category | Component | Project | Workspace) -> str:
    if isinstance(obj, Workspace):
        return obj.agreement
    if isinstance(obj, Project):
        return str(obj.get_effective_setting("agreement") or "")
    return obj.effective_agreement


@never_cache
@login_required
def agreement_confirm(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Component, Category, Project, Workspace))

    owner_lookup = get_agreement_owner_lookup(obj)
    if isinstance(obj, Component):
        has_agreed = ContributorAgreement.objects.has_agreed(request.user, obj)
    else:
        has_agreed = ContributorAgreement.objects.filter(
            user=request.user, **owner_lookup
        ).exists()

    if request.method == "POST":
        form = ContributorAgreementForm(request.POST)
        if form.is_valid() and not has_agreed:
            if isinstance(obj, Component):
                ContributorAgreement.objects.create(user=request.user, component=obj)
            else:
                ContributorAgreement.objects.create(user=request.user, **owner_lookup)
            return redirect_next(request.GET.get("next"), obj.get_absolute_url())
    else:
        form = ContributorAgreementForm(
            initial={"next": request.GET.get("next"), "confirm": has_agreed}
        )

    return render(
        request,
        "contributor-agreement.html",
        {
            "form": form,
            "object": obj,
            "agreement_text": get_agreement_text(obj),
            "has_agreed": has_agreed,
        },
    )
