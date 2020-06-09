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
from django.db.models import Count
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
from weblate.glossary.forms import (
    GlossaryForm,
    GlossaryUploadForm,
    LetterForm,
    OneTermForm,
    TermForm,
)
from weblate.glossary.models import Glossary, Term
from weblate.lang.models import Language
from weblate.trans.models import Change, Unit
from weblate.trans.util import redirect_next, render, sort_objects
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.ratelimit import session_ratelimit_post
from weblate.utils.site import get_site_url
from weblate.utils.views import get_paginator, get_project, import_message


def dict_title(prj, lang):
    """Return glossary title."""
    return _("%(language)s glossary for %(project)s") % {
        "language": lang,
        "project": prj,
    }


class LanguageGlossary:
    """Wrapper object for listing glossaries per language."""

    def __init__(self, project, post_data, user):
        self.project = project
        self.glossaries = (
            Glossary.objects.for_project(project).order_by("name").distinct()
        )
        self.data = {
            (item["term__language"], item["pk"]): item["term__count"]
            for item in self.glossaries.values("term__language", "pk").annotate(
                Count("term")
            )
        }
        try:
            self.post_id = int(post_data.get("edit_glossary", -1))
        except ValueError:
            self.post_id = -1
        self.languages = sort_objects(
            Language.objects.filter(translation__component__project=project).distinct()
        )
        self.forms = {
            glossary.id: GlossaryForm(
                user,
                glossary.project,
                post_data if self.post_id == glossary.id else None,
                instance=glossary,
                auto_id=f"id_edit_{glossary.id}_%s",
            )
            for glossary in self.glossaries
        }

    def get_edited_glossary(self):
        return self.glossaries.get(pk=self.post_id)

    def get_glossaries(self):
        for glossary in self.glossaries:
            glossaries = [
                {
                    "language": language,
                    "count": self.data.get((language.pk, glossary.pk), 0),
                }
                for language in self.languages
            ]

            yield {
                "glossary": glossary,
                "form": self.forms[glossary.id],
                "count": sum(g["count"] for g in glossaries),
                "glossaries": glossaries,
            }


@never_cache
def show_glossaries(request, project):
    obj = get_project(request, project)
    language_glossaries = LanguageGlossary(obj, request.POST, request.user)
    new_form = GlossaryForm(request.user, obj)
    if request.method == "POST" and request.user.has_perm("project.edit", obj):
        if "delete_glossary" in request.POST:
            try:
                glossary = language_glossaries.glossaries.get(
                    pk=int(request.POST["delete_glossary"])
                )
                glossary.delete()
                return redirect("show_glossaries", project=obj.slug)
            except (Glossary.DoesNotExist, ValueError):
                messages.error(request, _("Glossary was not found."))
        elif language_glossaries.post_id == -1:
            new_form = GlossaryForm(request.user, obj, data=request.POST)
            if new_form.is_valid():
                new_form.instance.project = obj
                new_form.save()
                return redirect("show_glossaries", project=obj.slug)
        else:
            try:
                glossary = language_glossaries.get_edited_glossary()
                form = language_glossaries.forms[glossary.id]
                if form.is_valid():
                    form.save()
                    return redirect("show_glossaries", project=obj.slug)
            except Glossary.DoesNotExist:
                messages.error(request, _("Glossary was not found."))

    return render(
        request,
        "glossaries.html",
        {
            "title": _("Glossaries"),
            "object": obj,
            "language_glossaries": language_glossaries.get_glossaries(),
            "project": obj,
            "new_form": new_form,
        },
    )


@never_cache
def edit_glossary(request, pk):
    term = get_object_or_404(Term, id=pk)
    if not term.check_perm(request.user, "glossary.edit"):
        raise PermissionDenied()

    if request.method == "POST":
        form = TermForm(term.glossary.project, data=request.POST, instance=term)
        if form.is_valid():
            term.edit(
                request,
                form.cleaned_data["source"],
                form.cleaned_data["target"],
                form.cleaned_data["glossary"],
            )
            return redirect_next(
                request.POST.get("next"),
                reverse(
                    "show_glossary",
                    kwargs={
                        "project": term.glossary.project.slug,
                        "lang": term.language.code,
                    },
                ),
            )
    else:
        form = TermForm(term.glossary.project, instance=term)

    last_changes = Change.objects.last_changes(request.user).filter(glossary_term=term)[
        :10
    ]

    return render(
        request,
        "edit_glossary.html",
        {
            "title": dict_title(term.glossary, term.language),
            "project": term.glossary.project,
            "language": term.language,
            "form": form,
            "next": request.POST.get("next") or request.GET.get("next"),
            "last_changes": last_changes,
            "last_changes_url": urlencode(
                (
                    ("project", term.glossary.project.slug),
                    ("lang", term.language.code),
                    ("action", Change.ACTION_DICTIONARY_NEW),
                    ("action", Change.ACTION_DICTIONARY_EDIT),
                    ("action", Change.ACTION_DICTIONARY_UPLOAD),
                )
            ),
        },
    )


@require_POST
@login_required
def delete_glossary(request, pk):
    term = get_object_or_404(Term, id=pk)
    if not term.check_perm(request.user, "glossary.delete"):
        raise PermissionDenied()

    term.delete()

    return redirect_next(
        request.POST.get("next"),
        reverse(
            "show_glossary",
            kwargs={"project": term.glossary.project.slug, "lang": term.language.code},
        ),
    )


@require_POST
@login_required
@session_ratelimit_post("glossary")
def upload_glossary(request, project, lang):
    prj = get_project(request, project)
    if not request.user.has_perm("glossary.upload", prj):
        raise PermissionDenied()
    lang = get_object_or_404(Language, code=lang)

    form = GlossaryUploadForm(prj, request.POST, request.FILES)
    if form.is_valid():
        try:
            count = Term.objects.upload(
                request,
                form.cleaned_data["glossary"],
                lang,
                request.FILES["file"],
                form.cleaned_data["method"],
            )
            import_message(
                request,
                count,
                _("No terms to import found in file."),
                ngettext(
                    "Imported %d term from the uploaded file.",
                    "Imported %d terms from the uploaded file.",
                    count,
                ),
            )
        except Exception as error:
            report_error(cause="Failed to handle upload")
            messages.error(request, _("File upload has failed: %s") % force_str(error))
    else:
        messages.error(request, _("Failed to process form!"))
    return redirect("show_glossary", project=prj.slug, lang=lang.code)


@never_cache
def download_glossary(request, project, lang):
    """Export glossary into various formats."""
    prj = get_project(request, project)
    lang = get_object_or_404(Language, code=lang)

    # Parse parameters
    export_format = None
    if "format" in request.GET:
        export_format = request.GET["format"]
    if export_format not in ("csv", "po", "tbx", "xliff"):
        export_format = "csv"

    # Grab all terms
    terms = Term.objects.for_project(prj).filter(language=lang).order()

    # Translate toolkit based export
    exporter = get_exporter(export_format)(
        prj,
        lang,
        get_site_url(
            reverse("show_glossary", kwargs={"project": prj.slug, "lang": lang.code})
        ),
        fieldnames=("source", "target"),
    )

    # Add terms
    for term in terms.iterator():
        exporter.add_glossary_term(term)

    # Save to response
    return exporter.get_response("glossary-{project}-{language}.{extension}")


@require_POST
@login_required
@session_ratelimit_post("glossary")
def add_glossary_term(request, unit_id):
    unit = get_object_or_404(Unit, pk=int(unit_id))
    request.user.check_access_component(unit.translation.component)

    prj = unit.translation.component.project
    lang = unit.translation.language

    code = 403
    results = ""
    terms = []

    if request.user.has_perm("glossary.add", prj):
        form = TermForm(prj, request.POST)
        if form.is_valid():
            term = Term.objects.create(
                request.user,
                language=lang,
                source=form.cleaned_data["source"],
                target=form.cleaned_data["target"],
                glossary=form.cleaned_data["glossary"],
            )
            terms = form.cleaned_data["terms"]
            terms.append(term.id)
            code = 200
            results = render_to_string(
                "snippets/glossary.html",
                {
                    "glossary": (
                        Term.objects.get_terms(unit).order()
                        | Term.objects.for_project(project=prj)
                        .filter(pk__in=terms)
                        .order()
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


@never_cache
@session_ratelimit_post("glossary")
def show_glossary(request, project, lang):
    prj = get_project(request, project)
    lang = get_object_or_404(Language, code=lang)

    if request.method == "POST" and request.user.has_perm("glossary.add", prj):
        form = TermForm(prj, request.POST)
        if form.is_valid():
            Term.objects.create(
                request.user,
                language=lang,
                source=form.cleaned_data["source"],
                target=form.cleaned_data["target"],
                glossary=form.cleaned_data["glossary"],
            )
        return redirect_next(request.POST.get("next"), request.get_full_path())
    form = TermForm(prj,)

    uploadform = GlossaryUploadForm(prj)

    terms = Term.objects.for_project(prj).filter(language=lang).order()

    letterform = LetterForm(request.GET)

    searchform = OneTermForm(request.GET)

    if searchform.is_valid() and searchform.cleaned_data["term"] != "":
        terms = terms.filter(source__substring=searchform.cleaned_data["term"])
        search = searchform.cleaned_data["term"]
    else:
        search = ""

    if letterform.is_valid() and letterform.cleaned_data["letter"] != "":
        terms = terms.filter(source__istartswith=letterform.cleaned_data["letter"])
        letter = letterform.cleaned_data["letter"]
    else:
        letter = ""

    terms = get_paginator(request, terms)

    last_changes = (
        Change.objects.last_changes(request.user)
        .filter(project=prj, language=lang)
        .exclude(glossary_term=None)[:10]
    )

    return render(
        request,
        "glossary.html",
        {
            "title": dict_title(prj, lang),
            "project": prj,
            "language": lang,
            "page_obj": terms,
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
