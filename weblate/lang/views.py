# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import permission_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.generic import CreateView, UpdateView

from weblate.lang.forms import LanguageForm, PluralForm
from weblate.lang.models import Language, Plural
from weblate.trans.forms import SearchForm, WorkflowSettingForm
from weblate.trans.models import Change, WorkflowSetting
from weblate.trans.models.project import prefetch_project_flags
from weblate.trans.util import sort_objects
from weblate.utils import messages
from weblate.utils.stats import (
    GlobalStats,
    ProjectLanguage,
    ProjectLanguageStats,
    prefetch_stats,
)
from weblate.utils.views import get_paginator

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def show_languages(request: AuthenticatedHttpRequest):
    custom_workflows = set()
    if request.user.has_perm("language.edit"):
        languages = Language.objects.all()
        custom_workflows = set(
            WorkflowSetting.objects.filter(project=None).values_list(
                "language_id", flat=True
            )
        )
    else:
        languages = Language.objects.have_translation()

    return render(
        request,
        "languages.html",
        {
            "allow_index": True,
            "languages": prefetch_stats(sort_objects(languages)),
            "custom_workflows": custom_workflows,
            "title": gettext("Languages"),
            "global_stats": GlobalStats(),
        },
    )


def show_language(request: AuthenticatedHttpRequest, lang):
    try:
        obj = Language.objects.get(code=lang)
    except Language.DoesNotExist as error:
        obj = Language.objects.fuzzy_get(lang)
        if isinstance(obj, Language):
            return redirect(obj)
        msg = "No Language matches the given query."
        raise Http404(msg) from error

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

    last_changes = Change.objects.last_changes(user, language=obj).recent()
    projects = prefetch_project_flags(
        get_paginator(
            request,
            user.allowed_projects.filter(
                component__translation__language=obj
            ).distinct(),
            stats=True,
        )
    )
    project_languages = [ProjectLanguage(project, obj) for project in projects]

    ProjectLanguageStats.prefetch_many([project.stats for project in project_languages])

    return render(
        request,
        "language.html",
        {
            "allow_index": True,
            "object": obj,
            "last_changes": last_changes,
            "search_form": SearchForm(user, language=obj),
            "projects": projects,
            "project_languages": project_languages,
        },
    )


@method_decorator(permission_required("language.add"), name="dispatch")
class CreateLanguageView(CreateView):
    template_name = "lang/create.html"

    def get_form(self, form_class=None):
        kwargs = self.get_form_kwargs()
        return (LanguageForm(**kwargs), PluralForm(**kwargs))

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):
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

    def get_context_data(self, **kwargs):
        """Insert the form into the context dict."""
        if "workflow_form" not in kwargs:
            kwargs["workflow_form"] = self.get_workflow_form()
        return super().get_context_data(**kwargs)

    def get_workflow_form(self):
        kwargs = self.get_form_kwargs()
        kwargs.pop("instance", None)
        kwargs.pop("initial", None)
        if self.workflow_object:
            kwargs["instance"] = self.workflow_object
        return WorkflowSettingForm(**kwargs)

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        self.object = self.get_object()
        try:
            self.workflow_object = self.object.workflowsetting_set.get(project=None)
        except WorkflowSetting.DoesNotExist:
            self.workflow_object = None
        return super().get(request, *args, **kwargs)

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        self.object = self.get_object()
        try:
            self.workflow_object = self.object.workflowsetting_set.get(project=None)
        except WorkflowSetting.DoesNotExist:
            self.workflow_object = None
        form = self.get_form()
        workflow_form = self.get_workflow_form()
        if form.is_valid() and workflow_form.is_valid():
            return self.form_valid(form, workflow_form)
        return self.render_to_response(
            self.get_context_data(form=form, workflow_form=workflow_form)
        )

    def form_valid(self, form, workflow_form):
        """If the form is valid, save the associated model."""
        workflow_form.instance.language = self.object
        self.workflow_object = workflow_form.save()
        return super().form_valid(form)


@method_decorator(permission_required("language.edit"), name="dispatch")
class EditPluralView(UpdateView):
    form_class = PluralForm
    model = Plural
