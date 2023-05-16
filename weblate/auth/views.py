# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.exceptions import PermissionDenied
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import UpdateView

from weblate.auth.forms import ProjectTeamForm, SitewideTeamForm
from weblate.auth.models import AutoGroup, Group
from weblate.trans.forms import UserAddTeamForm, UserManageForm
from weblate.trans.util import redirect_next
from weblate.utils.views import get_paginator, show_form_errors
from weblate.wladmin.forms import ChangedCharField


class TeamUpdateView(UpdateView):
    model = Group
    template_name = "auth/team.html"

    auto_formset = inlineformset_factory(
        Group,
        AutoGroup,
        fields=("match",),
        extra=0,
        field_classes={"match": ChangedCharField},
    )

    def get_form_class(self):
        if self.object.defining_project:
            return ProjectTeamForm
        return SitewideTeamForm

    def get_form(self, form_class=None):
        if not self.request.user.has_perm("meta:team.edit", self.object):
            return None
        return super().get_form(form_class)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object.defining_project:
            kwargs["project"] = self.object.defining_project
        return kwargs

    def get_object(self, queryset=None):
        result = super().get_object(queryset=queryset)
        user = self.request.user

        if (
            not user.has_perm("meta:team.edit", result)
            and not user.has_perm("meta:team.users", result)
            and not user.groups.filter(pk=result.pk).exists()
        ):
            raise PermissionDenied

        return result

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)

        if "auto_formset" not in result:
            result["auto_formset"] = self.auto_formset(instance=self.object)

        if self.request.user.has_perm("meta:team.users", self.object):
            result["users"] = get_paginator(
                self.request,
                self.object.user_set.filter(is_active=True, is_bot=False).order(),
            )
            result["add_user_form"] = UserAddTeamForm()
            result["admins"] = self.object.admins.all()

        return result

    def handle_add_user(self, request):
        form = UserAddTeamForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["make_admin"]:
                self.object.admins.add(form.cleaned_data["user"])
            else:
                self.object.admins.remove(form.cleaned_data["user"])
            form.cleaned_data["user"].groups.add(self.object)
        else:
            show_form_errors(request, form)
        return HttpResponseRedirect(self.get_success_url())

    def handle_remove_user(self, request):
        form = UserManageForm(request.POST)
        if form.is_valid():
            form.cleaned_data["user"].groups.remove(self.object)
        else:
            show_form_errors(request, form)
        return HttpResponseRedirect(self.get_success_url())

    def handle_delete(self, request):
        if self.object.defining_project:
            fallback = (
                reverse(
                    "manage-access",
                    kwargs={"project": self.object.defining_project.slug},
                )
                + "#teams"
            )
        elif request.user.is_superuser:
            fallback = reverse("manage-teams")
        else:
            fallback = reverse("manage_access") + "#teams"
        self.object.delete()
        return redirect_next(request.POST.get("next"), fallback)

    def post(self, request, **kwargs):
        self.object = self.get_object()
        if self.request.user.has_perm("meta:team.users", self.object):
            if "add_user" in request.POST:
                return self.handle_add_user(request)
            if "remove_user" in request.POST:
                return self.handle_remove_user(request)

        form = self.get_form()
        if form is None:
            return self.form_invalid(form, None)

        if "delete" in request.POST:
            return self.handle_delete(request)

        formset = self.auto_formset(instance=self.object, data=request.POST)
        if form.is_valid() and formset.is_valid():
            formset.save()
            return self.form_valid(form)
        return self.form_invalid(form, formset)

    def form_invalid(self, form, formset):
        """If the form is invalid, render the invalid form."""
        return self.render_to_response(
            self.get_context_data(form=form, auto_formset=formset)
        )
