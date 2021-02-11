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
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http.response import HttpResponseServerError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from weblate.checks.flags import Flags
from weblate.lang.models import Language
from weblate.trans.forms import ContextForm, MatrixLanguageForm
from weblate.trans.models import Unit
from weblate.trans.util import redirect_next, render
from weblate.utils import messages
from weblate.utils.views import get_component, show_form_errors


@require_POST
@login_required
def edit_context(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    if not unit.is_source and not unit.translation.component.is_glossary:
        raise Http404("Non source unit!")

    do_add = "addflag" in request.POST
    if do_add or "removeflag" in request.POST:
        if not request.user.has_perm("unit.flag", unit.translation):
            raise PermissionDenied()
        flag = request.POST.get("addflag", request.POST.get("removeflag"))
        flags = Flags(unit.extra_flags)
        if do_add:
            flags.merge(flag)
        else:
            flags.remove(flag)
        new_flags = flags.format()
        if new_flags != unit.extra_flags:
            unit.extra_flags = new_flags
            unit.save(same_content=True, update_fields=["extra_flags"])

    if not request.user.has_perm("source.edit", unit.translation):
        raise PermissionDenied()

    form = ContextForm(request.POST, instance=unit, user=request.user)

    if form.is_valid():
        form.save()
    else:
        messages.error(request, _("Failed to change additional string info!"))
        show_form_errors(request, form)

    return redirect_next(request.POST.get("next"), unit.get_absolute_url())


@login_required
def matrix(request, project, component):
    """Matrix view of all strings."""
    obj = get_component(request, project, component)

    show = False
    languages = None
    language_codes = None

    if "lang" in request.GET:
        form = MatrixLanguageForm(obj, request.GET)
        show = form.is_valid()
    else:
        form = MatrixLanguageForm(obj)

    if show:
        languages = Language.objects.filter(code__in=form.cleaned_data["lang"]).order()
        language_codes = ",".join(languages.values_list("code", flat=True))

    return render(
        request,
        "matrix.html",
        {
            "object": obj,
            "project": obj.project,
            "languages": languages,
            "language_codes": language_codes,
            "languages_form": form,
        },
    )


@login_required
def matrix_load(request, project, component):
    """Backend for matrix view of all strings."""
    obj = get_component(request, project, component)

    try:
        offset = int(request.GET.get("offset", ""))
    except ValueError:
        return HttpResponseServerError("Missing offset")
    language_codes = request.GET.get("lang")
    if not language_codes or offset is None:
        return HttpResponseServerError("Missing lang")

    # Can not use filter to keep ordering
    translations = [
        get_object_or_404(obj.translation_set, language__code=lang)
        for lang in language_codes.split(",")
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
