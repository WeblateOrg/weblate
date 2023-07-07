# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from weblate.glossary.forms import TermForm
from weblate.glossary.models import get_glossary_terms
from weblate.trans.models import Unit
from weblate.utils.ratelimit import session_ratelimit_post
from weblate.utils.views import get_form_errors


@require_POST
@login_required
@session_ratelimit_post("glossary")
def add_glossary_term(request, unit_id):
    unit = get_object_or_404(Unit, pk=int(unit_id))
    component = unit.translation.component
    user = request.user
    user.check_access_component(component)

    code = 403
    results = ""
    details = ""
    terms = []

    if user.has_perm("glossary.add", component.project):
        form = TermForm(unit, user, request.POST)
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
                        # distinct is needed as get_glossary_terms is distinct
                        # and mixed queries can not be combined
                        get_glossary_terms(unit)
                        | translation.unit_set.filter(pk__in=terms).distinct()
                    ),
                    "unit": unit,
                    "user": user,
                },
            )
        else:
            details = "\n".join(get_form_errors(form))

    return JsonResponse(
        data={
            "responseCode": code,
            "responseDetails": details,
            "results": results,
            "terms": ",".join(str(x) for x in terms),
        }
    )
