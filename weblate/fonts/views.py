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
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView

from weblate.fonts.forms import FontForm, FontGroupForm, FontOverrideForm
from weblate.fonts.models import Font, FontGroup
from weblate.utils import messages
from weblate.utils.views import ProjectViewMixin


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

    def post(self, request, **kwargs):
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied()
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
                instance.save()
                return redirect(instance)
            except ValidationError:
                messages.error(request, _("Entry by the same name already exists."))
        else:
            messages.error(request, _("Creation failed, please fix the errors below."))
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

    def post(self, request, **kwargs):
        self.object = self.get_object()
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied()

        self.object.delete()
        messages.error(request, _("Font deleted."))
        return redirect("fonts", project=self.project.slug)


@method_decorator(login_required, name="dispatch")
class FontGroupDetailView(ProjectViewMixin, DetailView):
    model = FontGroup
    _form = None
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

    def post(self, request, **kwargs):
        self.object = self.get_object()
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied()

        if "name" in request.POST:
            form = self._form = FontGroupForm(
                request.POST, instance=self.object, project=self.project
            )
            if form.is_valid():
                instance = form.save(commit=False)
                try:
                    instance.validate_unique()
                    instance.save()
                    return redirect(self.object)
                except ValidationError:
                    messages.error(request, _("Entry by the same name already exists."))
            return self.get(request, **kwargs)
        if "language" in request.POST:
            form = self._form = FontOverrideForm(request.POST)
            if form.is_valid():
                instance = form.save(commit=False)
                instance.group = self.object
                try:
                    instance.validate_unique()
                    instance.save()
                    return redirect(self.object)
                except ValidationError:
                    messages.error(request, _("Entry by the same name already exists."))
            return self.get(request, **kwargs)
        if "override" in request.POST:
            try:
                self.object.fontoverride_set.filter(
                    pk=int(request.POST["override"])
                ).delete()
                return redirect(self.object)
            except (ValueError, ObjectDoesNotExist):
                messages.error(request, _("No override found."))

        self.object.delete()
        messages.error(request, _("Font group deleted."))
        return redirect("fonts", project=self.project.slug)
