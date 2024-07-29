# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from weblate.trans.forms import ContributorAgreementForm
from weblate.trans.models import Component, ContributorAgreement
from weblate.trans.util import redirect_next
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@never_cache
@login_required
def agreement_confirm(request: AuthenticatedHttpRequest, path):
    component = parse_path(request, path, (Component,))

    has_agreed = ContributorAgreement.objects.has_agreed(request.user, component)

    if request.method == "POST":
        form = ContributorAgreementForm(request.POST)
        if form.is_valid() and not has_agreed:
            ContributorAgreement.objects.create(user=request.user, component=component)
            return redirect_next(request.GET.get("next"), component.get_absolute_url())
    else:
        form = ContributorAgreementForm(
            initial={"next": request.GET.get("next"), "confirm": has_agreed}
        )

    return render(
        request,
        "contributor-agreement.html",
        {"form": form, "object": component, "has_agreed": has_agreed},
    )
