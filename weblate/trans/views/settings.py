# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, View

from weblate.lang.models import Language
from weblate.trans.forms import (
    AnnouncementForm,
    ComponentDeleteForm,
    ComponentMoveForm,
    ComponentRenameForm,
    ComponentSettingsForm,
    ProjectDeleteForm,
    ProjectLanguageDeleteForm,
    ProjectRenameForm,
    ProjectSettingsForm,
    TranslationDeleteForm,
)
from weblate.trans.models import Announcement, Component
from weblate.trans.tasks import (
    component_removal,
    create_project_backup,
    project_removal,
)
from weblate.trans.util import redirect_param, render
from weblate.utils import messages
from weblate.utils.stats import ProjectLanguage
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
        raise Http404

    if request.method == "POST":
        settings_form = ProjectSettingsForm(request, request.POST, instance=obj)
        if settings_form.is_valid():
            settings_form.save()
            messages.success(request, _("Settings saved"))
            return redirect("settings", project=obj.slug)
        else:
            messages.error(
                request, _("Invalid settings. Please check the form for errors.")
            )
    else:
        settings_form = ProjectSettingsForm(request, instance=obj)

    return render(
        request,
        "project-settings.html",
        {"object": obj, "form": settings_form},
    )


@never_cache
@login_required
def change_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise Http404

    if request.method == "POST":
        form = ComponentSettingsForm(request, request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved"))
            return redirect("settings", project=obj.project.slug, component=obj.slug)
        else:
            messages.error(
                request, _("Invalid settings. Please check the form for errors.")
            )
            # Get a fresh copy of object, otherwise it will use unsaved changes
            # from the failed form
            obj = Component.objects.get(pk=obj.pk)
    else:
        form = ComponentSettingsForm(request, instance=obj)

    if obj.repo_needs_merge():
        messages.warning(
            request,
            _(
                "The repository is outdated. You might not get "
                "expected results until you update it."
            ),
        )

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
        raise Http404

    try:
        alert = obj.alert_set.get(name=request.POST["dismiss"])
        if alert.obj.dismissable:
            alert.dismissed = True
            alert.save(update_fields=["dismissed"])
    except ObjectDoesNotExist:
        pass

    return redirect_param(obj, "#alerts")


@login_required
@require_POST
def remove_translation(request, project, component, lang):
    obj = get_translation(request, project, component, lang)

    if not request.user.has_perm("translation.delete", obj):
        raise PermissionDenied

    form = TranslationDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    obj.remove(request.user)
    messages.success(request, _("The translation has been removed."))

    return redirect(obj.component)


@login_required
@require_POST
def remove_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise PermissionDenied

    form = ComponentDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    component_removal.delay(obj.pk, request.user.pk)
    messages.success(request, _("The translation component was scheduled for removal."))

    return redirect(obj.project)


@login_required
@require_POST
def remove_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("project.edit", obj):
        raise PermissionDenied

    form = ProjectDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    project_removal.delay(obj.pk, request.user.pk)
    messages.success(request, _("The project was scheduled for removal."))
    return redirect("home")


@login_required
@require_POST
def remove_project_language(request, project, lang):
    project_object = get_project(request, project)
    language_object = get_object_or_404(Language, code=lang)
    obj = ProjectLanguage(project_object, language_object)

    if not request.user.has_perm("translation.delete", obj):
        raise PermissionDenied

    form = ProjectLanguageDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#delete")

    for translation in obj.translation_set:
        translation.remove(request.user)

    messages.success(request, _("A language in the project was removed."))
    return redirect(project_object)


def perform_rename(form_cls, request, obj, perm: str):
    if not request.user.has_perm(perm, obj):
        raise PermissionDenied

    # Make sure any non-rename related issues are resolved first
    try:
        obj.full_clean()
    except ValidationError as err:
        messages.error(
            request,
            _("Cannot rename due to outstanding issue in the configuration: %s") % err,
        )
        return redirect_param(obj, "#rename")

    form = form_cls(request, request.POST, instance=obj)
    if not form.is_valid():
        show_form_errors(request, form)
        # Reload the object from DB to revert possible rejected change
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
        raise PermissionDenied

    form = AnnouncementForm(request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#announcement")

    Announcement.objects.create(
        user=request.user,
        project=obj.component.project,
        component=obj.component,
        language=obj.language,
        **form.cleaned_data,
    )

    return redirect(obj)


@login_required
@require_POST
def announcement_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.edit", obj):
        raise PermissionDenied

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
        raise PermissionDenied

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

    if request.user.has_perm("announcement.delete", announcement):
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


class BackupsMixin:
    @method_decorator(login_required)
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.obj = get_project(request, kwargs["project"])
        if not request.user.has_perm("project.edit", self.obj):
            raise PermissionDenied


class BackupsView(BackupsMixin, TemplateView):
    template_name = "trans/backups.html"

    def post(self, request, *args, **kwargs):
        create_project_backup.delay(self.obj.pk)
        messages.success(request, _("Backup scheduled. It will be available soon."))
        return redirect("backups", project=self.obj.slug)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["keep_count"] = settings.PROJECT_BACKUP_KEEP_COUNT
        context["keep_days"] = settings.PROJECT_BACKUP_KEEP_DAYS
        context["object"] = self.obj
        context["backups"] = self.obj.list_backups()
        return context


class BackupsDownloadView(BackupsMixin, View):
    def get(self, request, *args, **kwargs):
        for backup in self.obj.list_backups():
            if backup["name"] == kwargs["backup"]:
                return FileResponse(
                    open(backup["path"], "rb"),
                    as_attachment=True,
                    filename=backup["name"],
                )
        raise Http404
