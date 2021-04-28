#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from weblate.auth.models import User
from weblate.legal.forms import TOSForm
from weblate.legal.models import Agreement
from weblate.trans.util import redirect_next

MENU = (
    ("index", "legal:index", _("Overview")),
    ("terms", "legal:terms", _("Terms of Service")),
    ("cookies", "legal:cookies", _("Cookies")),
    ("privacy", "legal:privacy", _("Privacy")),
    ("contracts", "legal:contracts", _("Subcontractors")),
)


class LegalView(TemplateView):
    page = "index"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["legal_menu"] = MENU
        context["legal_page"] = self.page

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
def tos_confirm(request):
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

    return render(request, "legal/confirm.html", {"form": form})
