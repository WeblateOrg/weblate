#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

from django.core.exceptions import PermissionDenied
from django.forms import inlineformset_factory
from django.urls import reverse
from django.views.generic import UpdateView

from weblate.auth.forms import ProjectTeamForm, SitewideTeamForm
from weblate.auth.models import AutoGroup, Group
from weblate.trans.util import redirect_next
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
        else:
            return SitewideTeamForm

    def get_object(self, queryset=None):
        result = super().get_object(queryset=queryset)
        # Add permission check
        if self.request.user.has_perm("group.edit") or (
            result.defining_project
            and self.request.user.has_perm(
                "project.permissions", result.defining_project
            )
        ):
            return result

        raise PermissionDenied()

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)

        if "auto_formset" not in result:
            result["auto_formset"] = self.auto_formset(instance=self.object)

        return result

    def post(self, request, **kwargs):
        self.object = self.get_object()
        if "delete" in request.POST:
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

        form = self.get_form()
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
