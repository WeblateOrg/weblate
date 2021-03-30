#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
    if not unit.translation.is_source:
        raise Http404("Non source unit!")

    if not request.user.has_perm("source.edit", unit.translation.component):
        raise PermissionDenied()

    form = ContextForm(request.POST, instance=unit, user=request.user)

    if form.is_valid():
        form.save()
    else:
        messages.error(request, _("Failed to change a context!"))
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

    for unit in translations[0].unit_set.all()[offset : offset + 20]:
        units = []
        for translation in translations:
            try:
                units.append(translation.unit_set.get(id_hash=unit.id_hash))
            except Unit.DoesNotExist:
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
