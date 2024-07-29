# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.forms import inlineformset_factory
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import DetailView, UpdateView

from weblate.auth.forms import ProjectTeamForm, SitewideTeamForm
from weblate.auth.models import (
    AuthenticatedHttpRequest,
    AutoGroup,
    Group,
    Invitation,
    User,
)
from weblate.trans.forms import UserAddTeamForm, UserManageForm
from weblate.trans.util import redirect_next
from weblate.utils import messages
from weblate.utils.views import get_paginator, show_form_errors
from weblate.wladmin.forms import ChangedCharField


class TeamUpdateView(UpdateView):
    model = Group
    template_name = "auth/team.html"
    request: AuthenticatedHttpRequest

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

    def handle_add_user(self, request: AuthenticatedHttpRequest):
        form = UserAddTeamForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["make_admin"]:
                self.object.admins.add(form.cleaned_data["user"])
            else:
                self.object.admins.remove(form.cleaned_data["user"])
            form.cleaned_data["user"].add_team(request, self.object)
        else:
            show_form_errors(request, form)
        return HttpResponseRedirect(self.get_success_url())

    def handle_remove_user(self, request: AuthenticatedHttpRequest):
        form = UserManageForm(request.POST)
        if form.is_valid():
            form.cleaned_data["user"].remove_team(request, self.object)
        else:
            show_form_errors(request, form)
        return HttpResponseRedirect(self.get_success_url())

    def handle_delete(self, request: AuthenticatedHttpRequest):
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
        if self.object.internal and not self.object.defining_project:
            messages.error(request, gettext("Cannot remove built-in team!"))
        else:
            self.object.delete()
        return redirect_next(request.POST.get("next"), fallback)

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
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


class InvitationView(DetailView):
    model = Invitation

    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.user:
            # When inviting new user go through registration
            request.session["invitation_link"] = str(self.object.pk)
            return redirect("register")
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        self.object = invitation = self.get_object()
        user = request.user

        # Handle admin actions first
        action = request.POST.get("action", "")
        if action in {"resend", "remove"}:
            project = invitation.group.defining_project
            # Permission check
            if not user.has_perm(
                "project.permissions" if project else "user.edit", project
            ):
                raise PermissionDenied

            # Perform admin action
            if action == "resend":
                invitation.send_email()
                messages.success(request, gettext("User invitation e-mail was sent."))
            else:
                invitation.delete()
                messages.success(request, gettext("User invitation was removed."))

            # Redirect
            if project:
                return redirect("manage-access", project=project.slug)
            return redirect("manage-users")

        # Check if invitation can be accepted
        if not invitation.user:
            # This should go via registration path
            raise Http404
        if not user.is_authenticated:
            raise PermissionDenied
        if invitation.user != user:
            raise Http404

        # Accept invitation
        invitation.accept(request, user)

        if invitation.group.defining_project:
            return redirect(invitation.group.defining_project)
        return redirect("home")


def accept_invitation(
    request: AuthenticatedHttpRequest, invitation: Invitation, user: User | None
) -> None:
    if user is None:
        user = invitation.user
    if user is None:
        raise Http404

    # Add user to invited group
    user.add_team(request, invitation.group)
    # Let him watch the project
    if invitation.group.defining_project:
        user.profile.watched.add(invitation.group.defining_project)

    messages.success(
        request, gettext("Accepted invitation to the %s team.") % invitation.group
    )
    invitation.delete()
