# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.http.response import HttpResponseServerError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.checks.flags import Flags
from weblate.trans.forms import ContextForm, MatrixLanguageForm
from weblate.trans.models import Component, Unit
from weblate.trans.util import redirect_next, render
from weblate.utils import messages
from weblate.utils.views import parse_path, show_form_errors

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@require_POST
@login_required
@transaction.atomic
def edit_context(request: AuthenticatedHttpRequest, pk):
    unit = get_object_or_404(Unit, pk=pk)
    if not unit.is_source and not unit.translation.component.is_glossary:
        msg = "Non source unit!"
        raise Http404(msg)

    do_add = "addflag" in request.POST
    if do_add or "removeflag" in request.POST:
        if not request.user.has_perm("unit.flag", unit.translation):
            raise PermissionDenied
        flag = request.POST.get("addflag", request.POST.get("removeflag"))
        flags = unit.get_unit_flags()
        if (
            flag in {"terminology", "forbidden", "read-only"}
            and not unit.is_source
            and flag not in flags
        ):
            unit = unit.source_unit
            flags = Flags(unit.extra_flags)
        if do_add:
            flags.merge(flag)
        else:
            flags.remove(flag)
        new_flags = flags.format()
        if new_flags != unit.extra_flags:
            unit.extra_flags = new_flags
            unit.save(same_content=True, update_fields=["extra_flags"])
    else:
        if not request.user.has_perm("source.edit", unit.translation):
            raise PermissionDenied

        form = ContextForm(request.POST, instance=unit, user=request.user)

        if form.is_valid():
            form.save()
        else:
            messages.error(request, gettext("Could not change additional string info!"))
            show_form_errors(request, form)

    return redirect_next(request.POST.get("next"), unit.get_absolute_url())


@login_required
def matrix(request: AuthenticatedHttpRequest, path):
    """Matrix view of all strings."""
    obj = parse_path(request, path, (Component,))

    show = False
    translations = None
    language_codes_url = None

    if "lang" in request.GET:
        form = MatrixLanguageForm(obj, request.GET)
        show = form.is_valid()
    else:
        form = MatrixLanguageForm(obj)

    if show:
        translations = (
            obj.translation_set.filter(language__code__in=form.cleaned_data["lang"])
            .select_related("language")
            .order()
        )
        language_codes_url = "&".join(
            f"lang={translation.language.code}" for translation in translations
        )

    return render(
        request,
        "matrix.html",
        {
            "object": obj,
            "project": obj.project,
            "component": obj,
            "translations": translations,
            "language_codes_url": language_codes_url,
            "languages_form": form,
        },
    )


@login_required
def matrix_load(request: AuthenticatedHttpRequest, path):
    """Backend for matrix view of all strings."""
    obj = parse_path(request, path, (Component,))

    try:
        offset = int(request.GET.get("offset", ""))
    except ValueError:
        return HttpResponseServerError("Missing offset")
    form = MatrixLanguageForm(obj, request.GET)
    if not form.is_valid():
        return HttpResponseServerError("Missing lang")
    language_codes = form.cleaned_data["lang"]

    # Can not use filter to keep ordering
    translations = [
        get_object_or_404(obj.translation_set, language__code=lang)
        for lang in language_codes
    ]

    data = []

    source_units = obj.source_translation.unit_set.order()[offset : offset + 20]
    source_ids = [unit.pk for unit in source_units]

    translated_units = [
        {
            unit.source_unit_id: unit
            for unit in translation.unit_set.order().filter(source_unit__in=source_ids)
        }
        for translation in translations
    ]

    for unit in source_units:
        units = []
        # Avoid need to fetch source unit again
        unit.source_unit = unit
        for translation in translated_units:
            if unit.pk in translation:
                # Avoid need to fetch source unit again
                translation[unit.pk].source_unit = unit
                units.append(translation[unit.pk])
            else:
                units.append(None)

        data.append((unit, units))

    return render(
        request,
        "matrix-table.html",
        {
            "object": obj,
            "data": data,
            "last": translations[0].unit_set.count() <= offset + 20,
        },
    )
