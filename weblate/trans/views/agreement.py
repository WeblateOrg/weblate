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


from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from weblate.trans.forms import ContributorAgreementForm
from weblate.trans.models import ContributorAgreement
from weblate.trans.util import redirect_next
from weblate.utils.views import get_component


@never_cache
@login_required
def agreement_confirm(request, project, component):
    component = get_component(request, project, component)

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
