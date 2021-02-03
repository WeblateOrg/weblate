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


from django.contrib.auth.decorators import permission_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.generic import CreateView, UpdateView

from weblate.lang.forms import LanguageForm, PluralForm
from weblate.lang.models import Language, Plural
from weblate.trans.forms import ProjectLanguageDeleteForm, SearchForm
from weblate.trans.models import Change
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.util import sort_objects
from weblate.utils import messages
from weblate.utils.stats import (
    GlobalStats,
    ProjectLanguage,
    ProjectLanguageStats,
    prefetch_stats,
)
from weblate.utils.views import get_project, optional_form


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
    projects = prefetch_project_flags(
        prefetch_stats(projects.filter(component__translation__language=obj).distinct())
    )
    projects = [ProjectLanguage(project, obj) for project in projects]

    ProjectLanguageStats.prefetch_many([project.stats for project in projects])

    return render(
        request,
        "language.html",
        {
            "allow_index": True,
            "object": obj,
            "last_changes": last_changes,
            "last_changes_url": urlencode({"lang": obj.code}),
            "projects": projects,
        },
    )


def show_project(request, lang, project):
    try:
        language_object = Language.objects.get(code=lang)
    except Language.DoesNotExist:
        language_object = Language.objects.fuzzy_get(lang)
        if isinstance(language_object, Language):
            return redirect(language_object)
        raise Http404("No Language matches the given query.")

    project_object = get_project(request, project)
    obj = ProjectLanguage(project_object, language_object)
    user = request.user

    last_changes = Change.objects.last_changes(user).filter(
        language=language_object, project=project_object
    )[:10]

    return render(
        request,
        "language-project.html",
        {
            "allow_index": True,
            "language": language_object,
            "project": project_object,
            "object": obj,
            "last_changes": last_changes,
            "last_changes_url": urlencode(
                {"lang": language_object.code, "project": project_object.slug}
            ),
            "translations": obj.translation_set,
            "title": f"{project_object} - {language_object}",
            "search_form": SearchForm(user, language=language_object),
            "licenses": project_object.component_set.exclude(license="").order_by(
                "license"
            ),
            "language_stats": project_object.stats.get_single_language_stats(
                language_object
            ),
            "delete_form": optional_form(
                ProjectLanguageDeleteForm, user, "translation.delete", obj, obj=obj
            ),
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
