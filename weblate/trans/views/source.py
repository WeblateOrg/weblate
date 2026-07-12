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
    unit = get_object_or_404(Unit.objects.filter_access(request.user), pk=pk)
    if not unit.is_source and not unit.translation.component.is_glossary:
        msg = "Non source unit!"
        raise Http404(msg)

    do_add = "addflag" in request.POST
    if do_add or "removeflag" in request.POST:
        if not request.user.has_perm("meta:unit.flag", unit.translation):
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
            unit.update_extra_flags(new_flags, request.user)
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

    translations_by_code = {
        translation.language.code: translation
        for translation in obj.translation_set.filter(
            language__code__in=language_codes
        ).select_related("language", "plural")
    }
    try:
        # The selected language order defines the matrix column order.
        translations = [translations_by_code[code] for code in language_codes]
    except KeyError as error:
        raise Http404 from error

    source_translation = obj.source_translation
    source_units = list(source_translation.unit_set.order()[offset : offset + 21])
    last = len(source_units) <= 20
    source_units = source_units[:20]
    source_ids = [unit.pk for unit in source_units]

    translations_by_id = {translation.pk: translation for translation in translations}
    translated_units = {translation.pk: {} for translation in translations}
    for unit in Unit.objects.filter(
        translation_id__in=translations_by_id,
        source_unit_id__in=source_ids,
    ).order():
        # Reuse the translations fetched above, including their related objects.
        unit.translation = translations_by_id[unit.translation_id]
        translated_units[unit.translation_id][unit.source_unit_id] = unit

    data = []
    for unit in source_units:
        # Avoid need to fetch source unit again
        unit.source_unit = unit
        units = []
        for translation in translations:
            translated_unit = translated_units[translation.pk].get(unit.pk)
            if translated_unit is not None:
                # Avoid need to fetch source unit again
                translated_unit.source_unit = unit
            units.append(translated_unit)

        data.append((unit, units))

    return render(
        request,
        "matrix-table.html",
        {
            "object": obj,
            "data": data,
            "last": last,
        },
    )
