# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import permission_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.generic import CreateView, UpdateView

from weblate.lang.forms import LanguageForm, PluralForm
from weblate.lang.models import Language, Plural
from weblate.trans.forms import SearchForm
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
            "title": gettext("Languages"),
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

    user = request.user

    if request.method == "POST" and user.has_perm("language.edit"):
        if obj.translation_set.exists():
            messages.error(
                request, gettext("Remove all translations using this language first.")
            )
        else:
            obj.delete()
            messages.success(request, gettext("Language %s removed.") % obj)
            return redirect("languages")

    last_changes = Change.objects.last_changes(user).filter(language=obj)[:10].preload()
    projects = user.allowed_projects
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
            "search_form": SearchForm(user, language=obj),
            "projects": projects,
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
