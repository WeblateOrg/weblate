#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.trans.forms import (
    AnnouncementForm,
    ComponentDeleteForm,
    ComponentMoveForm,
    ComponentRenameForm,
    ComponentSettingsForm,
    ProjectDeleteForm,
    ProjectRenameForm,
    ProjectSettingsForm,
    TranslationDeleteForm,
)
from weblate.trans.models import Announcement, Change
from weblate.trans.tasks import component_removal, project_removal
from weblate.trans.util import redirect_param, render
from weblate.utils import messages
from weblate.utils.views import (
    get_component,
    get_project,
    get_translation,
    show_form_errors,
)


@never_cache
@login_required
def change_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise Http404()

    if request.method == "POST":
        settings_form = ProjectSettingsForm(request, request.POST, instance=obj)
        if settings_form.is_valid():
            settings_form.save()
            messages.success(request, _("Settings saved"))
            return redirect("settings", project=obj.slug)
        else:
            messages.error(
                request, _("Invalid settings, please check the form for errors!")
            )
    else:
        settings_form = ProjectSettingsForm(request, instance=obj)

    return render(
        request,
        "project-settings.html",
        {"object": obj, "settings_form": settings_form},
    )


@never_cache
@login_required
def change_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise Http404()

    if request.method == "POST":
        form = ComponentSettingsForm(request, request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved"))
            return redirect("settings", project=obj.project.slug, component=obj.slug)
        else:
            messages.error(
                request, _("Invalid settings, please check the form for errors!")
            )
    else:
        form = ComponentSettingsForm(request, instance=obj)

    return render(
        request,
        "component-settings.html",
        {"project": obj.project, "object": obj, "form": form},
    )


@never_cache
@login_required
@require_POST
def dismiss_alert(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise Http404()

    alert = obj.alert_set.get(name=request.POST["dismiss"])
    if alert.obj.dismissable:
        alert.dismissed = True
        alert.save(update_fields=["dismissed"])

    return redirect_param(obj, "#alerts")


@login_required
@require_POST
def remove_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("translation.delete", obj):
        raise PermissionDenied()

    form = TranslationDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    obj.remove(request.user)
    messages.success(request, _("Translation has been removed."))

    return redirect(obj.component)


@login_required
@require_POST
def remove_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise PermissionDenied()

    form = ComponentDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    component_removal.delay(obj.pk, request.user.pk)
    messages.success(request, _("Translation component was scheduled for removal."))

    return redirect(obj.project)


@login_required
@require_POST
def remove_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied()

    form = ProjectDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    project_removal.delay(obj.pk, request.user.pk)
    messages.success(request, _("Project was scheduled for removal."))
    return redirect("home")


def perform_rename(form_cls, request, obj, perm: str):
    if not request.user.has_perm(perm, obj):
        raise PermissionDenied()

    form = form_cls(request, request.POST, instance=obj)
    if not form.is_valid():
        show_form_errors(request, form)
        # Reload the object from db to revert possible rejected change
        obj.refresh_from_db()
        return redirect_param(obj, "#rename")

    # Invalidate old stats
    obj.stats.invalidate()

    obj = form.save()
    # Invalidate new stats
    obj.stats.invalidate()

    return redirect(obj)


@login_required
@require_POST
def rename_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_rename(ComponentRenameForm, request, obj, "component.edit")


@login_required
@require_POST
def move_component(request, project, component):
    obj = get_component(request, project, component)
    return perform_rename(ComponentMoveForm, request, obj, "project.edit")


@login_required
@require_POST
def rename_project(request, project):
    obj = get_project(request, project)
    return perform_rename(ProjectRenameForm, request, obj, "project.edit")


@login_required
@require_POST
def announcement_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("component.edit", obj):
        raise PermissionDenied()

    form = AnnouncementForm(request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#announcement")

    Announcement.objects.create(
        user=request.user,
        project=obj.component.project,
        component=obj.component,
        language=obj.language,
        **form.cleaned_data
    )

    return redirect(obj)


@login_required
@require_POST
def announcement_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise PermissionDenied()

    form = AnnouncementForm(request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#announcement")

    Announcement.objects.create(
        user=request.user, project=obj.project, component=obj, **form.cleaned_data
    )

    return redirect(obj)


@login_required
@require_POST
def announcement_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied()

    form = AnnouncementForm(request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#announcement")

    Announcement.objects.create(user=request.user, project=obj, **form.cleaned_data)

    return redirect(obj)


@login_required
@require_POST
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)

    if request.user.has_perm(
        "component.edit", announcement.component
    ) or request.user.has_perm("project.edit", announcement.project):
        announcement.delete()

    return JsonResponse({"responseStatus": 200})


@login_required
def component_progress(request, project, component):
    obj = get_component(request, project, component)
    return_url = "component" if "info" in request.GET else "guide"
    if not obj.in_progress():
        return redirect(return_url, **obj.get_reverse_url_kwargs())

    progress, log = obj.get_progress()

    return render(
        request,
        "component-progress.html",
        {
            "object": obj,
            "progress": progress,
            "log": "\n".join(log),
            "return_url": return_url,
        },
    )


@require_POST
@login_required
def component_progress_terminate(request, project, component):
    obj = get_component(request, project, component)

    if obj.in_progress and request.user.has_perm("component.edit", obj):
        obj.background_task.revoke(terminate=True)

    return redirect(obj)


@login_required
def component_progress_js(request, project, component):
    obj = get_component(request, project, component)
    progress, log = obj.get_progress()
    return JsonResponse(
        {"in_progress": obj.in_progress(), "progress": progress, "log": "\n".join(log)}
    )
