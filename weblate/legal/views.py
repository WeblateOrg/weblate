# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.legal.forms import TOSForm
from weblate.legal.models import Agreement
from weblate.trans.util import redirect_next

MENU = (
    ("index", "legal:index", gettext_lazy("Overview")),
    ("terms", "legal:terms", gettext_lazy("General Terms and Conditions")),
    ("cookies", "legal:cookies", gettext_lazy("Cookies")),
    ("privacy", "legal:privacy", gettext_lazy("Privacy Policy")),
    ("contracts", "legal:contracts", gettext_lazy("Subcontractors")),
)


class LegalView(TemplateView):
    page = "index"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["legal_menu"] = MENU
        context["legal_page"] = self.page
        context["privacy_url"] = reverse("legal:privacy")
        context["terms_url"] = reverse("legal:terms")

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
        {"form": form, "privacy_url": reverse("legal:privacy")},
    )
