# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.generic import DetailView, ListView, View

from weblate.fonts.forms import FontForm, FontGroupForm, FontOverrideForm
from weblate.fonts.models import Font, FontGroup
from weblate.trans.models import Project
from weblate.utils import messages
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class ProjectViewMixin(View):
    def setup(self, request: AuthenticatedHttpRequest, *args, **kwargs) -> None:
        super().setup(request, *args, **kwargs)
        self.project = parse_path(request, [self.kwargs["project"]], (Project,))


@method_decorator(login_required, name="dispatch")
class FontListView(ProjectViewMixin, ListView):
    model = Font
    _font_form = None
    _group_form = None

    def get_queryset(self):
        return self.project.font_set.order_by("family", "style")

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = self.project
        result["font_list"] = result["object_list"]
        result["group_list"] = self.project.fontgroup_set.order()
        result["font_form"] = self._font_form or FontForm()
        result["group_form"] = self._group_form or FontGroupForm(
            auto_id="id_group_%s", project=self.project
        )
        result["can_edit"] = self.request.user.has_perm("project.edit", self.project)
        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied
        form: FontForm | FontGroupForm
        if request.FILES:
            form = self._font_form = FontForm(request.POST, request.FILES)
        else:
            form = self._group_form = FontGroupForm(
                request.POST, auto_id="id_group_%s", project=self.project
            )
        if form.is_valid():
            instance = form.save(commit=False)
            instance.project = self.project
            instance.user = self.request.user
            try:
                instance.validate_unique()
            except ValidationError:
                messages.error(
                    request, gettext("Font with the same name already exists.")
                )
            else:
                instance.save()
                return redirect(instance)
        else:
            messages.error(
                request, gettext("Creation failed, please fix the errors below.")
            )
        return self.get(request, **kwargs)


@method_decorator(login_required, name="dispatch")
class FontDetailView(ProjectViewMixin, DetailView):
    model = Font

    def get_queryset(self):
        return self.project.font_set.all()

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["can_edit"] = self.request.user.has_perm("project.edit", self.project)
        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        self.object = self.get_object()
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied

        self.object.delete()
        messages.error(request, gettext("Font deleted."))
        return redirect("fonts", project=self.project.slug)


@method_decorator(login_required, name="dispatch")
class FontGroupDetailView(ProjectViewMixin, DetailView):
    model = FontGroup
    _form: FontOverrideForm | FontGroupForm | None = None
    _override_form = None

    def get_queryset(self):
        return self.project.fontgroup_set.all()

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["form"] = self._form or FontGroupForm(
            instance=self.object, project=self.project
        )
        result["override_form"] = self._override_form or FontOverrideForm()
        result["can_edit"] = self.request.user.has_perm("project.edit", self.project)
        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        self.object = self.get_object()
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied

        form: FontOverrideForm | FontGroupForm
        if "name" in request.POST:
            form = self._form = FontGroupForm(
                request.POST, instance=self.object, project=self.project
            )
            if form.is_valid():
                instance = form.save(commit=False)
                try:
                    instance.validate_unique()
                except ValidationError:
                    messages.error(
                        request,
                        gettext("Font group with the same name already exists."),
                    )
                else:
                    instance.save()
                    return redirect(self.object)
            return self.get(request, **kwargs)
        if "language" in request.POST:
            form = self._form = FontOverrideForm(request.POST)
            if form.is_valid():
                instance = form.save(commit=False)
                instance.group = self.object
                try:
                    instance.validate_unique()
                except ValidationError:
                    messages.error(
                        request,
                        gettext("Font group with the same name already exists."),
                    )
                else:
                    instance.save()
                    return redirect(self.object)

            return self.get(request, **kwargs)
        if "override" in request.POST:
            try:
                self.object.fontoverride_set.filter(
                    pk=int(request.POST["override"])
                ).delete()
            except (ValueError, ObjectDoesNotExist):
                messages.error(request, gettext("No override found."))
            else:
                return redirect(self.object)

        self.object.delete()
        messages.error(request, gettext("Font group deleted."))
        return redirect("fonts", project=self.project.slug)
