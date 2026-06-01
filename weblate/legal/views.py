# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from weblate.auth.models import User
from weblate.legal.forms import TOSForm
from weblate.legal.models import Agreement
from weblate.legal.utils import (
    get_document_context,
    get_legal_menu,
    is_document_hidden,
)
from weblate.trans.util import redirect_next

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@method_decorator(login_not_required, name="dispatch")
class LegalView(TemplateView):
    page = "index"

    def dispatch(self, request, *args, **kwargs):
        if is_document_hidden(self.page):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["legal_menu"] = get_legal_menu()
        context["legal_page"] = self.page
        context["legal_document_css_class"] = settings.LEGAL_DOCUMENT_CSS_CLASS
        context.update(get_document_context())

        return context

    def get_template_names(self):
        return [f"legal/{self.page}.html"]


class TermsView(LegalView):
    page = "terms"


class CookiesView(LegalView):
    page = "cookies"


class PrivacyView(LegalView):
    page = "privacy"


class ContractsView(LegalView):
    page = "contracts"


@never_cache
@login_not_required
def tos_confirm(request: AuthenticatedHttpRequest):
    user = None
    if request.user.is_authenticated:
        user = request.user
    elif "tos_user" in request.session:
        user = User.objects.get(pk=request.session["tos_user"])

    if user is None:
        return redirect("home")

    agreement = Agreement.objects.get_or_create(user=user)[0]
    if agreement.is_current():
        return redirect_next(request.GET.get("next"), "home")

    if request.method == "POST":
        form = TOSForm(request.POST)
        if form.is_valid():
            agreement.make_current(request)
            return redirect_next(form.cleaned_data["next"], "home")
    else:
        form = TOSForm(initial={"next": request.GET.get("next")})

    return render(
        request,
        "legal/confirm.html",
        {
            "form": form,
            "legal_document_css_class": settings.LEGAL_DOCUMENT_CSS_CLASS,
            **get_document_context(),
        },
    )
