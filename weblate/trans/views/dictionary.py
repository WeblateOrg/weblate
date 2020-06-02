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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.formats.exporters import get_exporter
from weblate.lang.models import Language
from weblate.trans.forms import DictUploadForm, LetterForm, OneWordForm, WordForm
from weblate.trans.models import Change, Dictionary, Unit
from weblate.trans.util import redirect_next, redirect_param, render, sort_objects
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.ratelimit import session_ratelimit_post
from weblate.utils.site import get_site_url
from weblate.utils.views import get_paginator, get_project, import_message


def dict_title(prj, lang):
    """Return dictionary title."""
    return _("%(language)s glossary for %(project)s") % {
        "language": lang,
        "project": prj,
    }


@never_cache
def show_dictionaries(request, project):
    obj = get_project(request, project)
    return render(
        request,
        "dictionaries.html",
        {
            "title": _("Glossaries"),
            "object": obj,
            "dicts": sort_objects(
                Language.objects.filter(translation__component__project=obj).distinct()
            ),
            "project": obj,
        },
    )


@never_cache
def edit_dictionary(request, project, lang, pk):
    prj = get_project(request, project)
    if not request.user.has_perm("glossary.edit", prj):
        raise PermissionDenied()
    lang = get_object_or_404(Language, code=lang)
    word = get_object_or_404(Dictionary, project=prj, language=lang, id=pk)

    if request.method == "POST":
        form = WordForm(request.POST)
        if form.is_valid():
            word.edit(request, form.cleaned_data["source"], form.cleaned_data["target"])
            return redirect("show_dictionary", project=prj.slug, lang=lang.code)
    else:
        form = WordForm(initial={"source": word.source, "target": word.target})

    last_changes = Change.objects.last_changes(request.user).filter(dictionary=word)[
        :10
    ]

    return render(
        request,
        "edit_dictionary.html",
        {
            "title": dict_title(prj, lang),
            "project": prj,
            "language": lang,
            "form": form,
            "last_changes": last_changes,
            "last_changes_url": urlencode(
                (
                    ("project", prj.slug),
                    ("lang", lang.code),
                    ("action", Change.ACTION_DICTIONARY_NEW),
                    ("action", Change.ACTION_DICTIONARY_EDIT),
                    ("action", Change.ACTION_DICTIONARY_UPLOAD),
                )
            ),
        },
    )


@require_POST
@login_required
def delete_dictionary(request, project, lang, pk):
    prj = get_project(request, project)
    if not request.user.has_perm("glossary.delete", prj):
        raise PermissionDenied()

    lang = get_object_or_404(Language, code=lang)
    word = get_object_or_404(Dictionary, project=prj, language=lang, id=pk)

    word.delete()

    params = {}
    for param in ("letter", "limit", "page"):
        if param in request.POST:
            params[param] = request.POST[param]

    if params:
        param = "?" + urlencode(params)
    else:
        param = ""

    return redirect_param("show_dictionary", param, project=prj.slug, lang=lang.code)


@require_POST
@login_required
@session_ratelimit_post("glossary")
def upload_dictionary(request, project, lang):
    prj = get_project(request, project)
    if not request.user.has_perm("glossary.upload", prj):
        raise PermissionDenied()
    lang = get_object_or_404(Language, code=lang)

    form = DictUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            count = Dictionary.objects.upload(
                request, prj, lang, request.FILES["file"], form.cleaned_data["method"]
            )
            import_message(
                request,
                count,
                _("No words to import found in file."),
                ngettext(
                    "Imported %d word from the uploaded file.",
                    "Imported %d words from the uploaded file.",
                    count,
                ),
            )
        except Exception as error:
            report_error(cause="Failed to handle upload")
            messages.error(request, _("File upload has failed: %s") % force_str(error))
    else:
        messages.error(request, _("Failed to process form!"))
    return redirect("show_dictionary", project=prj.slug, lang=lang.code)


@never_cache
def download_dictionary(request, project, lang):
    """Export dictionary into various formats."""
    prj = get_project(request, project)
    lang = get_object_or_404(Language, code=lang)

    # Parse parameters
    export_format = None
    if "format" in request.GET:
        export_format = request.GET["format"]
    if export_format not in ("csv", "po", "tbx", "xliff"):
        export_format = "csv"

    # Grab all words
    words = Dictionary.objects.filter(project=prj, language=lang).order()

    # Translate toolkit based export
    exporter = get_exporter(export_format)(
        prj,
        lang,
        get_site_url(
            reverse("show_dictionary", kwargs={"project": prj.slug, "lang": lang.code})
        ),
        fieldnames=("source", "target"),
    )

    # Add words
    for word in words.iterator():
        exporter.add_dictionary(word)

    # Save to response
    return exporter.get_response("glossary-{project}-{language}.{extension}")


@require_POST
@login_required
@session_ratelimit_post("glossary")
def add_dictionary(request, unit_id):
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access_component(unit.translation.component)

    prj = unit.translation.component.project
    lang = unit.translation.language

    code = 403
    results = ""
    words = []

    if request.user.has_perm("glossary.add", prj):
        form = WordForm(request.POST)
        if form.is_valid():
            word = Dictionary.objects.create(
                request.user,
                project=prj,
                language=lang,
                source=form.cleaned_data["source"],
                target=form.cleaned_data["target"],
            )
            words = form.cleaned_data["words"]
            words.append(word.id)
            code = 200
            results = render_to_string(
                "snippets/glossary.html",
                {
                    "glossary": (
                        Dictionary.objects.get_words(unit).order()
                        | Dictionary.objects.filter(project=prj, pk__in=words).order()
                    ),
                    "unit": unit,
                    "user": request.user,
                },
            )

    return JsonResponse(
        data={
            "responseCode": code,
            "results": results,
            "words": ",".join(str(x) for x in words),
        }
    )


@never_cache
@session_ratelimit_post("glossary")
def show_dictionary(request, project, lang):
    prj = get_project(request, project)
    lang = get_object_or_404(Language, code=lang)

    if request.method == "POST" and request.user.has_perm("glossary.add", prj):
        form = WordForm(request.POST)
        if form.is_valid():
            Dictionary.objects.create(
                request.user,
                project=prj,
                language=lang,
                source=form.cleaned_data["source"],
                target=form.cleaned_data["target"],
            )
        return redirect_next(request.POST.get("next"), request.get_full_path())
    form = WordForm()

    uploadform = DictUploadForm()

    words = Dictionary.objects.filter(project=prj, language=lang).order()

    letterform = LetterForm(request.GET)

    searchform = OneWordForm(request.GET)

    if searchform.is_valid() and searchform.cleaned_data["term"] != "":
        words = words.filter(source__substring=searchform.cleaned_data["term"])
        search = searchform.cleaned_data["term"]
    else:
        search = ""

    if letterform.is_valid() and letterform.cleaned_data["letter"] != "":
        words = words.filter(source__istartswith=letterform.cleaned_data["letter"])
        letter = letterform.cleaned_data["letter"]
    else:
        letter = ""

    words = get_paginator(request, words)

    last_changes = (
        Change.objects.last_changes(request.user)
        .filter(project=prj, language=lang)
        .exclude(dictionary=None)[:10]
    )

    return render(
        request,
        "dictionary.html",
        {
            "title": dict_title(prj, lang),
            "project": prj,
            "language": lang,
            "page_obj": words,
            "form": form,
            "query_string": urlencode({"term": search, "letter": letter}),
            "uploadform": uploadform,
            "letterform": letterform,
            "searchform": searchform,
            "letter": letter,
            "last_changes": last_changes,
            "last_changes_url": urlencode(
                (
                    ("project", prj.slug),
                    ("lang", lang.code),
                    ("action", Change.ACTION_DICTIONARY_NEW),
                    ("action", Change.ACTION_DICTIONARY_EDIT),
                    ("action", Change.ACTION_DICTIONARY_UPLOAD),
                )
            ),
        },
    )
