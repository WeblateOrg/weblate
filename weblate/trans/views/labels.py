# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.trans.forms import LabelForm
from weblate.trans.models import Label, Project
from weblate.trans.util import render
from weblate.utils.views import parse_path


@login_required
@never_cache
def project_labels(request, project):
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

    if request.method == "POST":
        form = LabelForm(request.POST)
        if form.is_valid():
            form.instance.project = obj
            form.save()
            return redirect("labels", project=project)
    else:
        form = LabelForm()

    return render(
        request,
        "project-labels.html",
        {
            "object": obj,
            "project": obj,
            "form": form,
            "labels": obj.label_set.annotate(string_count=Count("unit__id")),
        },
    )


@login_required
@never_cache
def label_edit(request, project, pk):
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

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
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

    label = get_object_or_404(Label, pk=pk, project=obj)

    label.delete()

    return redirect("labels", project=project)
