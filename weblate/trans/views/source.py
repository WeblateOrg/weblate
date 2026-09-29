# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.http.response import HttpResponseServerError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.trans.forms import ContextForm, MatrixLanguageForm, UnitFlagsForm
from weblate.trans.models import Component, Unit
from weblate.trans.util import redirect_next, render
from weblate.utils import messages
from weblate.utils.views import parse_path, show_form_errors

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User


def get_locked_unit(user: User, pk: int) -> Unit:
    """Lock a unit and its source in the same order for every context edit."""
    unit = get_object_or_404(Unit.objects.filter_access(user), pk=pk)
    # Lock both units in a consistent order for all scoped operations.
    locked = {
        item.pk: item
        for item in Unit.objects.filter(pk__in={unit.pk, unit.source_unit_id})
        .order_by("pk")
        .select_for_update()
    }
    if not {unit.pk, unit.source_unit_id}.issubset(locked):
        msg = "Unit was removed while processing the request"
        raise Http404(msg)
    unit = locked[unit.pk]
    unit.source_unit = locked[cast("int", unit.source_unit_id)]
    return unit


@require_POST
@login_required
@transaction.atomic
def edit_context(request: AuthenticatedHttpRequest, pk):
    unit = get_locked_unit(request.user, pk)
    source = unit.source_unit

    operations = {"addflag", "removeflag", "promoteflag"} & request.POST.keys()
    if operations:
        if len(operations) != 1:
            msg = "Invalid flag action"
            raise Http404(msg)
        action = operations.pop()
        flag = request.POST[action]
        scope = request.POST.get("scope", "source" if unit.is_source else "translation")
        if scope not in {"source", "translation"} or flag not in {
            "read-only",
            "forbidden",
            "terminology",
        }:
            msg = "Invalid flag action"
            raise Http404(msg)
        if flag != "read-only" and not unit.translation.component.is_glossary:
            msg = "Invalid glossary flag"
            raise Http404(msg)
        if flag == "terminology" and scope != "source":
            msg = "Terminology is source-wide"
            raise Http404(msg)
        if action == "promoteflag" and (
            flag != "read-only" or unit.is_source or scope != "source"
        ):
            msg = "Invalid flag promotion"
            raise Http404(msg)
        target = source if scope == "source" else unit
        targets = [source, unit] if action == "promoteflag" else [target]
        if not all(
            request.user.has_perm("meta:unit.flag", item.translation)
            for item in targets
        ):
            raise PermissionDenied
        flags = target.get_unit_flags()
        if action == "removeflag":
            flags.remove(flag)
        else:
            flags.merge(flag)
        target.update_extra_flags(flags.format(), request.user)
        if action == "promoteflag":
            # The source save has updated this translation's derived state.
            unit.refresh_from_db()
            unit.source_unit = source
            unit.store_old_unit(unit)
            flags = unit.get_unit_flags()
            flags.remove(flag)
            unit.update_extra_flags(flags.format(), request.user)
    elif "edit_flags" in request.POST:
        if not any(
            request.user.has_perm("meta:unit.flag", item.translation)
            for item in (source, unit)
        ):
            raise PermissionDenied
        form = UnitFlagsForm(request.POST, unit=unit, user=request.user)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, gettext("Could not change string flags!"))
            show_form_errors(request, form)
    else:
        if not unit.is_source and not unit.translation.component.is_glossary:
            msg = "Non source unit!"
            raise Http404(msg)
        if not request.user.has_perm("source.edit", unit.translation):
            raise PermissionDenied
        context_form = ContextForm(
            request.POST,
            instance=unit,
            user=request.user,
            include_flags="extra_flags" in request.POST,
        )
        if context_form.is_valid():
            context_form.save()
        else:
            messages.error(request, gettext("Could not change additional string info!"))
            show_form_errors(request, context_form)

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
