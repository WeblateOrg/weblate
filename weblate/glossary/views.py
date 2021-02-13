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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from weblate.glossary.forms import TermForm
from weblate.glossary.models import get_glossary_terms
from weblate.trans.models import Unit
from weblate.utils.ratelimit import session_ratelimit_post


@require_POST
@login_required
@session_ratelimit_post("glossary")
def add_glossary_term(request, unit_id):
    unit = get_object_or_404(Unit, pk=int(unit_id))
    component = unit.translation.component
    request.user.check_access_component(component)

    code = 403
    results = ""
    terms = []

    if request.user.has_perm("glossary.add", component.project):
        form = TermForm(unit, request.POST)
        if form.is_valid():
            translation = form.cleaned_data["translation"]
            context = ""
            suffix = 0
            source = form.cleaned_data["source"]
            while translation.unit_set.filter(context=context, source=source).exists():
                suffix += 1
                context = str(suffix)
            translation.add_units(
                request, [(context, source, form.cleaned_data["target"])]
            )
            terms = form.cleaned_data["terms"]
            terms.append(translation.unit_set.get(context=context, source=source).pk)
            code = 200
            results = render_to_string(
                "snippets/glossary.html",
                {
                    "glossary": (
                        # distinct is needed as get_glossary_terms is distict
                        # and mixed queries can not be combined
                        get_glossary_terms(unit)
                        | translation.unit_set.filter(pk__in=terms).distinct()
                    ),
                    "unit": unit,
                    "user": request.user,
                },
            )

    return JsonResponse(
        data={
            "responseCode": code,
            "results": results,
            "terms": ",".join(str(x) for x in terms),
        }
    )
