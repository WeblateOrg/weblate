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


from django.contrib.auth.decorators import permission_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.generic import CreateView, UpdateView

from weblate.lang import data
from weblate.lang.forms import LanguageForm, PluralForm
from weblate.lang.models import Language, Plural
from weblate.trans.forms import SearchForm
from weblate.trans.models import Change
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.util import sort_objects
from weblate.utils import messages
from weblate.utils.stats import GlobalStats, ProjectLanguageStats, prefetch_stats
from weblate.utils.views import get_paginator, get_project


def show_languages(request):
    if request.user.has_perm("language.edit"):
        languages = Language.objects.all()
    else:
        languages = Language.objects.have_translation()
    return render(
        request,
        "languages.html",
        {
            "allow_index": True,
            "languages": prefetch_stats(sort_objects(languages)),
            "title": _("Languages"),
            "global_stats": GlobalStats(),
        },
    )


def show_language(request, lang):
    try:
        obj = Language.objects.get(code=lang)
    except Language.DoesNotExist:
        obj = Language.objects.fuzzy_get(lang)
        if isinstance(obj, Language):
            return redirect(obj)
        raise Http404("No Language matches the given query.")

    if request.method == "POST" and request.user.has_perm("language.edit"):
        if obj.translation_set.exists():
            messages.error(
                request, _("Remove all translations using this language first.")
            )
        else:
            obj.delete()
            messages.success(request, _("Language %s removed.") % obj)
            return redirect("languages")

    last_changes = Change.objects.last_changes(request.user).filter(language=obj)[:10]
    projects = request.user.allowed_projects
    dicts = projects.filter(glossary__term__language=obj).distinct()
    projects = prefetch_project_flags(
        prefetch_stats(projects.filter(component__translation__language=obj).distinct())
    )

    stats = []
    for project in projects:
        project.language_stats = project.stats.get_single_language_stats(obj)
        stats.append(project.language_stats)
    ProjectLanguageStats.prefetch_many(stats)

    return render(
        request,
        "language.html",
        {
            "allow_index": True,
            "object": obj,
            "last_changes": last_changes,
            "last_changes_url": urlencode({"lang": obj.code}),
            "dicts": dicts,
            "projects": projects,
        },
    )


def show_project(request, lang, project):
    try:
        obj = Language.objects.get(code=lang)
    except Language.DoesNotExist:
        obj = Language.objects.fuzzy_get(lang)
        if isinstance(obj, Language):
            return redirect(obj)
        raise Http404("No Language matches the given query.")

    pobj = get_project(request, project)

    last_changes = Change.objects.last_changes(request.user).filter(
        language=obj, project=pobj
    )[:10]

    # Paginate translations.
    translation_list = (
        obj.translation_set.prefetch()
        .filter(component__project=pobj)
        .order_by("component__name")
    )
    translations = get_paginator(request, translation_list)

    return render(
        request,
        "language-project.html",
        {
            "allow_index": True,
            "language": obj,
            "project": pobj,
            "last_changes": last_changes,
            "last_changes_url": urlencode({"lang": obj.code, "project": pobj.slug}),
            "translations": translations,
            "title": "{0} - {1}".format(pobj, obj),
            "search_form": SearchForm(request.user),
            "licenses": pobj.component_set.exclude(license="").order_by("license"),
            "language_stats": pobj.stats.get_single_language_stats(obj),
        },
    )


@method_decorator(permission_required("language.add"), name="dispatch")
class CreateLanguageView(CreateView):
    template_name = "lang/create.html"

    def get_form(self, form_class=None):
        kwargs = self.get_form_kwargs()
        return (LanguageForm(**kwargs), PluralForm(**kwargs))

    def post(self, request, *args, **kwargs):
        self.object = None
        forms = self.get_form()
        if all(form.is_valid() for form in forms):
            return self.form_valid(forms)
        return self.form_invalid(forms)

    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        self.object = form[0].save()
        plural = form[1].instance
        plural.language = self.object
        plural.type = data.PLURAL_UNKNOWN
        plural.source = Plural.SOURCE_DEFAULT
        plural.save()
        return redirect(self.object)


@method_decorator(permission_required("language.edit"), name="dispatch")
class EditLanguageView(UpdateView):
    form_class = LanguageForm
    model = Language


@method_decorator(permission_required("language.edit"), name="dispatch")
class EditPluralView(UpdateView):
    form_class = PluralForm
    model = Plural
