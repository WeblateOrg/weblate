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
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.trans.forms import LabelForm
from weblate.trans.models import Label
from weblate.trans.util import render
from weblate.utils.views import get_project


@login_required
@never_cache
def project_labels(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied()

    if request.method == "POST":
        form = LabelForm(request.POST)
        if form.is_valid():
            form.instance.project = obj
            form.save()
            return redirect("labels", project=project)
    else:
        form = LabelForm()

    return render(
        request, "project-labels.html", {"object": obj, "project": obj, "form": form}
    )


@login_required
@never_cache
def label_edit(request, project, pk):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied()

    label = get_object_or_404(Label, pk=pk, project=obj)

    if request.method == "POST":
        form = LabelForm(request.POST, instance=label)
        if form.is_valid():
            form.save()
            return redirect("labels", project=project)
    else:
        form = LabelForm(instance=label)

    return render(
        request,
        "project-label-edit.html",
        {"object": obj, "project": obj, "form": form},
    )


@login_required
@never_cache
@require_POST
def label_delete(request, project, pk):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied()

    label = get_object_or_404(Label, pk=pk, project=obj)

    label.delete()

    return redirect("labels", project=project)
