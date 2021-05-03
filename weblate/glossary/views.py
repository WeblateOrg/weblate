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
from django.utils.translation import gettext as _
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
    details = ""
    terms = []

    if request.user.has_perm("glossary.add", component.project):
        form = TermForm(unit, request.POST)
        if form.is_valid():
            translation = form.cleaned_data["translation"]
            added = translation.add_unit(request, **form.as_kwargs())
            terms = form.cleaned_data["terms"]
            terms.append(added.pk)
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
        else:
            messages = []
            for error in form.non_field_errors():
                messages.append(error)
            for field in form:
                for error in field.errors:
                    messages.append(
                        _("Error in parameter %(field)s: %(error)s")
                        % {"field": field.name, "error": error},
                    )
            details = "\n".join(messages)

    return JsonResponse(
        data={
            "responseCode": code,
            "responseDetails": details,
            "results": results,
            "terms": ",".join(str(x) for x in terms),
        }
    )
