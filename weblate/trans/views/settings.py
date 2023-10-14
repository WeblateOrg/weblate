# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, View

from weblate.trans.forms import (
    AddCategoryForm,
    AnnouncementForm,
    BaseDeleteForm,
    CategoryMoveForm,
    CategoryRenameForm,
    ComponentMoveForm,
    ComponentRenameForm,
    ComponentSettingsForm,
    ProjectRenameForm,
    ProjectSettingsForm,
    WorkflowSettingForm,
)
from weblate.trans.models import (
    Announcement,
    Category,
    Component,
    Project,
    Translation,
    WorkflowSetting,
)
from weblate.trans.tasks import (
    category_removal,
    component_removal,
    create_project_backup,
    project_removal,
)
from weblate.trans.util import redirect_param, render
from weblate.utils import messages
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import parse_path, show_form_errors


@never_cache
@login_required
def change(request, path):
    obj = parse_path(request, path, (Component, Project, ProjectLanguage))
    if not request.user.has_perm(obj.settings_permission, obj):
        raise Http404

    if isinstance(obj, Component):
        return change_component(request, obj)
    if isinstance(obj, ProjectLanguage):
        return change_project_language(request, obj)
    return change_project(request, obj)


def change_project(request, obj):
    if request.method == "POST":
        settings_form = ProjectSettingsForm(request, request.POST, instance=obj)
        if settings_form.is_valid():
            settings_form.save()
            messages.success(request, gettext("Settings saved"))
            return redirect("settings", path=obj.get_url_path())
        messages.error(
            request, gettext("Invalid settings. Please check the form for errors.")
        )
    else:
        settings_form = ProjectSettingsForm(request, instance=obj)

    return render(
        request,
        "project-settings.html",
        {"object": obj, "form": settings_form},
    )


def change_project_language(request, obj):
    try:
        instance = obj.project.workflowsetting_set.get(language=obj.language)
    except WorkflowSetting.DoesNotExist:
        instance = None

    if request.method == "POST":
        settings_form = WorkflowSettingForm(request.POST, instance=instance)
        if settings_form.is_valid():
            settings_form.instance.project = obj.project
            settings_form.instance.language = obj.language
            settings_form.save()
            messages.success(request, gettext("Settings saved"))
            return redirect("settings", path=obj.get_url_path())
        messages.error(
            request, gettext("Invalid settings. Please check the form for errors.")
        )
    else:
        settings_form = WorkflowSettingForm(instance=instance)

    return render(
        request,
        "project-language-settings.html",
        {"object": obj, "form": settings_form},
    )


def change_component(request, obj):
    if not request.user.has_perm("component.edit", obj):
        raise Http404

    if request.method == "POST":
        form = ComponentSettingsForm(request, request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, gettext("Settings saved"))
            return redirect("settings", path=obj.get_url_path())
        messages.error(
            request, gettext("Invalid settings. Please check the form for errors.")
        )
        # Get a fresh copy of object, otherwise it will use unsaved changes
        # from the failed form
        obj = Component.objects.get(pk=obj.pk)
    else:
        form = ComponentSettingsForm(request, instance=obj)

    if obj.repo_needs_merge():
        messages.warning(
            request,
            gettext(
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
def dismiss_alert(request, path):
    obj = parse_path(request, path, (Component,))

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
def remove(request, path):
    obj = parse_path(
        request,
        path,
        (Translation, Component, Project, ProjectLanguage, CategoryLanguage, Category),
    )

    if not request.user.has_perm(obj.remove_permission, obj):
        raise PermissionDenied

    form = BaseDeleteForm(obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#organize")

    if isinstance(obj, Translation):
        parent = obj.component
        obj.remove(request.user)
        messages.success(request, gettext("The translation has been removed."))
    elif isinstance(obj, Component):
        parent = obj.category or obj.project
        component_removal.delay(obj.pk, request.user.pk)
        messages.success(
            request, gettext("The translation component was scheduled for removal.")
        )
    elif isinstance(obj, Category):
        parent = obj.category or obj.project
        category_removal.delay(obj.pk, request.user.pk)
        messages.success(request, gettext("The category was scheduled for removal."))
    elif isinstance(obj, Project):
        parent = reverse("home")
        project_removal.delay(obj.pk, request.user.pk)
        messages.success(request, gettext("The project was scheduled for removal."))
    elif isinstance(obj, ProjectLanguage):
        parent = obj.project
        for translation in obj.translation_set:
            translation.remove(request.user)

        messages.success(request, gettext("A language in the project was removed."))
    elif isinstance(obj, CategoryLanguage):
        parent = obj.project
        for translation in obj.translation_set:
            translation.remove(request.user)

        messages.success(request, gettext("A language in the category was removed."))

    return redirect(parent)


def perform_rename(form_cls, request, obj, perm: str):
    if not request.user.has_perm(perm, obj):
        raise PermissionDenied

    # Make sure any non-rename related issues are resolved first
    try:
        obj.full_clean()
    except ValidationError as err:
        messages.error(
            request,
            gettext("Could not change %s due to outstanding issue in its settings: %s")
            % (obj, err),
        )
        return redirect_param(obj, "#organize")

    form = form_cls(request, request.POST, instance=obj)
    if not form.is_valid():
        show_form_errors(request, form)
        # Reload the object from DB to revert possible rejected change
        obj.refresh_from_db()
        return redirect_param(obj, "#organize")

    # Invalidate old stats
    old_stats = list(obj.stats.get_update_objects())

    obj = form.save()

    # Invalidate new stats
    obj.stats.update_parents(old_stats)

    return redirect(obj)


@login_required
@require_POST
def move(request, path):
    obj = parse_path(request, path, (Component, Category))
    if isinstance(obj, Category):
        return perform_rename(CategoryMoveForm, request, obj, "project.edit")
    return perform_rename(ComponentMoveForm, request, obj, "project.edit")


@login_required
@require_POST
def rename(request, path):
    obj = parse_path(request, path, (Component, Project, Category))
    if isinstance(obj, Component):
        return perform_rename(ComponentRenameForm, request, obj, "component.edit")
    if isinstance(obj, Category):
        return perform_rename(CategoryRenameForm, request, obj, "project.edit")
    return perform_rename(ProjectRenameForm, request, obj, "project.edit")


@login_required
@require_POST
def add_category(request, path):
    obj = parse_path(request, path, (Project, Category))
    if not request.user.has_perm("project.edit", obj) or not obj.can_add_category:
        raise PermissionDenied
    form = AddCategoryForm(request, obj, request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#organize")
    form.save()
    return redirect(form.instance)


@login_required
@require_POST
def announcement(request, path):
    obj = parse_path(request, path, (Translation, Component, Project))

    if not request.user.has_perm("component.edit", obj):
        raise PermissionDenied

    form = AnnouncementForm(request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj, "#announcement")

    # Scope specific attributes
    scope = {}
    if isinstance(obj, Translation):
        scope["project"] = obj.component.project
        scope["component"] = obj.component
        scope["language"] = obj.language
    elif isinstance(obj, Component):
        scope["project"] = obj.project
        scope["component"] = obj
    elif isinstance(obj, Project):
        scope["project"] = obj

    Announcement.objects.create(
        user=request.user,
        **scope,
        **form.cleaned_data,
    )

    return redirect(obj)


@login_required
@require_POST
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)

    if request.user.has_perm("announcement.delete", announcement):
        announcement.delete()

    return JsonResponse({"responseStatus": 200})


@login_required
def component_progress(request, path):
    obj = parse_path(request, path, (Component,))
    return_url = "show" if "info" in request.GET else "guide"
    if not obj.in_progress():
        return redirect(return_url, path=obj.get_url_path())

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
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.obj = parse_path(request, [kwargs["project"]], (Project,))
        if not request.user.has_perm("project.edit", self.obj):
            raise PermissionDenied


@method_decorator(login_required, name="dispatch")
class BackupsView(BackupsMixin, TemplateView):
    template_name = "trans/backups.html"

    def post(self, request, *args, **kwargs):
        create_project_backup.delay(self.obj.pk)
        messages.success(
            request, gettext("Backup scheduled. It will be available soon.")
        )
        return redirect("backups", project=self.obj.slug)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["keep_count"] = settings.PROJECT_BACKUP_KEEP_COUNT
        context["keep_days"] = settings.PROJECT_BACKUP_KEEP_DAYS
        context["object"] = self.obj
        context["backups"] = self.obj.list_backups()
        return context


@method_decorator(login_required, name="dispatch")
class BackupsDownloadView(BackupsMixin, View):
    def get(self, request, *args, **kwargs):
        for backup in self.obj.list_backups():
            if backup["name"] == kwargs["backup"]:
                return FileResponse(
                    open(backup["path"], "rb"),  # noqa: SIM115
                    as_attachment=True,
                    filename=backup["name"],
                )
        raise Http404
