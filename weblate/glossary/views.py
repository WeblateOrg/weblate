# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@require_POST
@login_required
@session_ratelimit_post("glossary")
def add_glossary_term(request: AuthenticatedHttpRequest, unit_id):
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
            # Only append the new term if it's not already in the list
            if added.pk not in terms:
                terms.append(added.pk)
            code = 200

            # Fetch matching terms
            all_terms = get_glossary_terms(unit)

            # Create a set of existing term IDs
            existing_term_ids = {term.pk for term in all_terms}

            # Add newly added term if not already present
            if added.pk not in existing_term_ids:
                all_terms.append(added)
                existing_term_ids.add(added.pk)

            # Add any missing terms that aren't already present
            missing_terms = set(terms) - existing_term_ids
            if missing_terms:
                all_terms.extend(translation.unit_set.filter(pk__in=missing_terms))

            results = render_to_string(
                "snippets/glossary.html",
                {
                    "glossary": all_terms,
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
