# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Count, Exists, OuterRef, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext, ngettext
from django.views.generic.base import TemplateView

from weblate.lang.models import Language
from weblate.memory.forms import DeleteForm, UploadForm
from weblate.memory.models import Memory, MemoryImportError, MemoryScope
from weblate.memory.tasks import import_memory
from weblate.memory.utils import (
    CATEGORY_FILE,
    CATEGORY_PRIVATE_OFFSET,
    CATEGORY_SHARED,
    CATEGORY_USER_OFFSET,
)
from weblate.metrics.models import Metric
from weblate.trans.models import Component, Project
from weblate.utils import messages
from weblate.utils.views import ErrorFormView, parse_path
from weblate.wladmin.views import MENU
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User

CD_TEMPLATE = 'attachment; filename="weblate-memory.{}"'


class ObjectsDict(TypedDict):
    project: NotRequired[Project]
    workspace: NotRequired[Workspace]
    from_file: NotRequired[bool]
    user: NotRequired[User]


class UploadObjectsDict(TypedDict):
    project: NotRequired[Project]
    from_file: NotRequired[bool]
    user: NotRequired[User]


def get_objects(request: AuthenticatedHttpRequest, kwargs) -> ObjectsDict:
    if "project" in kwargs:
        return {"project": parse_path(request, [kwargs["project"]], (Project,))}
    if "workspace" in kwargs:
        workspace = get_object_or_404(Workspace, pk=kwargs["workspace"])
        if not request.user.has_perm("workspace.edit", workspace):
            msg = "Access denied"
            raise Http404(msg)
        return {"workspace": workspace}
    if "manage" in kwargs:
        return {"from_file": True}
    return {"user": request.user}


def check_perm(user: User, permission: str, objects: ObjectsDict):
    if "workspace" in objects:
        return user.has_perm("workspace.edit", objects["workspace"])
    if "project" in objects:
        return user.has_perm(permission, objects["project"])
    if "user" in objects:
        # User can edit own translation memory
        return True
    if "from_file" in objects:
        return user.has_perm(permission)
    return False


def get_scope_delete_query(objects: ObjectsDict) -> Q:
    if "workspace" in objects:
        return Q(
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=objects["workspace"],
        )
    if "project" in objects:
        project = objects["project"]
        return Q(
            scope__in=(MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_PROJECT_FILE),
            project=project,
        )
    if "user" in objects:
        user = objects["user"]
        return Q(
            scope__in=(MemoryScope.SCOPE_USER, MemoryScope.SCOPE_USER_FILE), user=user
        )
    if "from_file" in objects:
        return Q(scope=MemoryScope.SCOPE_GLOBAL_FILE)
    return Q(pk__isnull=True)


def get_language_filter(request: AuthenticatedHttpRequest, name: str) -> int | None:
    value = request.GET.get(name)
    if value is None:
        return None
    if not value.isdecimal():
        msg = gettext("Invalid language identifier.")
        raise Http404(msg)
    return int(value)


def get_export_category(objects: ObjectsDict) -> int | None:
    if "workspace" in objects:
        # The JSON memory format has no workspace category.
        return 0
    if "project" in objects:
        return CATEGORY_PRIVATE_OFFSET + objects["project"].pk
    if "user" in objects:
        return CATEGORY_USER_OFFSET + objects["user"].pk
    if "from_file" in objects:
        return CATEGORY_FILE
    return None


@method_decorator(login_required, name="dispatch")
class MemoryFormView(ErrorFormView):
    def get_success_url(self):
        if "manage" in self.kwargs:
            return reverse("manage-memory")
        return reverse("memory", kwargs=self.kwargs)

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        self.objects = get_objects(request, kwargs)
        return super().dispatch(request, *args, **kwargs)


class DeleteView(MemoryFormView):
    form_class = DeleteForm
    request: AuthenticatedHttpRequest

    def form_valid(self, form):
        if not check_perm(self.request.user, "memory.delete", self.objects):
            raise PermissionDenied
        entries = Memory.objects.filter_type(**self.objects)
        if "origin" in self.request.POST:
            entries = entries.filter(origin=self.request.POST["origin"])
        entries.using("default").delete_scope(get_scope_delete_query(self.objects))
        messages.success(self.request, gettext("Entries were deleted."))
        return super().form_valid(form)


class RebuildView(MemoryFormView):
    form_class = DeleteForm
    request: AuthenticatedHttpRequest

    def form_valid(self, form):
        if not check_perm(self.request.user, "memory.delete", self.objects) or not (
            {"project", "workspace"} & self.objects.keys()
        ):
            raise PermissionDenied
        origin = self.request.POST.get("origin")
        if "workspace" in self.objects:
            return self.rebuild_workspace(origin, form)

        project = self.objects["project"]
        component_id = None
        if origin:
            try:
                component_id = project.component_set.get_by_path(origin).id
            except ObjectDoesNotExist as error:
                raise PermissionDenied from error
        # Delete private entries
        entries = Memory.objects.filter_type(**self.objects).exclude(
            legacy_from_file=True
        )
        if origin:
            entries = entries.filter(origin=origin)
        entries.using("default").delete_scope(
            Q(scope=MemoryScope.SCOPE_PROJECT, project=project)
        )
        # Delete possible shared entries
        if origin:
            slugs = [origin]
        else:
            slugs = [
                component.full_slug for component in project.component_set.prefetch()
            ]
        Memory.objects.filter(origin__in=slugs).using("default").delete_scope(
            Q(
                scope__in=(MemoryScope.SCOPE_SHARED, MemoryScope.SCOPE_WORKSPACE),
                source_project=project,
            ),
            delete_legacy=False,
        )
        # Rebuild memory in background
        import_memory.delay(project_id=project.id, component_id=component_id)
        messages.success(
            self.request,
            gettext(
                "Translation memory entries created from current translations "
                "were deleted and will be rebuilt in the background. Uploaded "
                "entries were preserved."
            ),
        )
        return super().form_valid(form)

    def rebuild_workspace(self, origin: str | None, form):
        workspace = self.objects["workspace"]
        component = None
        projects = workspace.projects.filter(contribute_workspace_tm=True)
        if not workspace.contribute_workspace_tm:
            projects = projects.none()
        if origin:
            try:
                component = Component.objects.filter(project__in=projects).get_by_path(
                    origin
                )
            except ObjectDoesNotExist as error:
                raise PermissionDenied from error

        entries = Memory.objects.filter_type(workspace=workspace)
        if origin:
            entries = entries.filter(origin=origin)
        entries.using("default").delete_scope(
            Q(scope=MemoryScope.SCOPE_WORKSPACE, workspace=workspace),
            delete_legacy=False,
        )

        if component is not None:
            import_memory.delay(
                project_id=component.project_id, component_id=component.id
            )
        else:
            for project_id in projects.values_list("id", flat=True):
                import_memory.delay(project_id=project_id, component_id=None)
        messages.success(
            self.request,
            gettext(
                "Translation memory entries created from current translations "
                "were deleted and will be rebuilt in the background."
            ),
        )
        return super().form_valid(form)


class UploadView(MemoryFormView):
    form_class = UploadForm
    request: AuthenticatedHttpRequest

    def form_valid(self, form):
        if "workspace" in self.objects or not check_perm(
            self.request.user, "memory.edit", self.objects
        ):
            raise PermissionDenied
        upload_objects = cast("UploadObjectsDict", self.objects)
        try:
            count = Memory.objects.import_file(
                request=self.request,
                fileobj=form.cleaned_data["file"],
                source_language=form.cleaned_data["source_language"],
                target_language=form.cleaned_data["target_language"],
                **upload_objects,
            )
            messages.success(
                self.request,
                ngettext(
                    "Processed %(count)d active translation memory entry.",
                    "Processed %(count)d active translation memory entries.",
                    count,
                )
                % {"count": count},
            )
        except MemoryImportError as error:
            messages.error(self.request, str(error))
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class MemoryView(TemplateView):
    template_name = "memory/index.html"
    request: AuthenticatedHttpRequest
    objects: ObjectsDict

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        self.objects = get_objects(request, kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_url(self, name):
        if "manage" in self.kwargs:
            return reverse(f"manage-{name}")
        return reverse(name, kwargs=self.kwargs)

    @cached_property
    def entries(self):
        return Memory.objects.filter_type(**self.objects)

    @cached_property
    def component_slugs(self) -> set[str]:
        if "workspace" in self.objects:
            workspace = self.objects["workspace"]
            if not workspace.contribute_workspace_tm:
                return set()
            components = Component.objects.filter(
                project__workspace=workspace,
                project__contribute_workspace_tm=True,
            ).prefetch()
        else:
            components = self.objects["project"].component_set.prefetch()
        return {component.full_slug for component in components}

    def get_rebuild_entries(self):
        if "workspace" in self.objects:
            workspace = self.objects["workspace"]
            return Memory.objects.using(self.entries.db).filter_scope(
                Q(scope=MemoryScope.SCOPE_WORKSPACE, workspace=workspace)
            )
        project = self.objects["project"]
        scope_query = Q(scope=MemoryScope.SCOPE_PROJECT, project=project)
        if self.component_slugs:
            scope_query |= Q(
                scope__in=(MemoryScope.SCOPE_SHARED, MemoryScope.SCOPE_WORKSPACE),
                source_project=project,
                memory__origin__in=self.component_slugs,
            )
        return Memory.objects.using(self.entries.db).filter_scope(scope_query)

    @cached_property
    def rebuild_counts(self) -> dict[str, int]:
        return {
            entry["origin"]: entry["id__count"]
            for entry in self.get_rebuild_entries()
            .values("origin")
            .order_by("origin")
            .annotate(Count("id"))
        }

    def get_origins(self):
        def get_url(slug: str) -> str:
            if "/" not in slug:
                return ""
            return reverse("show", kwargs={"path": slug.split("/")})

        file_scopes = (
            MemoryScope.SCOPE_GLOBAL_FILE,
            MemoryScope.SCOPE_PROJECT_FILE,
            MemoryScope.SCOPE_USER_FILE,
        )
        file_scope = MemoryScope.objects.using(self.entries.db).none()
        if "workspace" not in self.objects:
            file_scope = MemoryScope.objects.using(self.entries.db).filter(
                memory_id=OuterRef("pk"), scope__in=file_scopes
            )
        entries = (
            self.entries.annotate(has_file_scope=Exists(file_scope))
            .values("origin", "has_file_scope")
            .order_by("origin")
            .annotate(Count("id"))
        )
        from_file = []
        result = []
        for entry in entries:
            if entry.pop("has_file_scope"):
                from_file.append(entry)
            else:
                result.append(entry)
        for entry in result:
            entry["url"] = get_url(entry["origin"])
        if {"project", "workspace"} & self.objects.keys():
            existing = {entry["origin"] for entry in result}
            for entry in result:
                entry["can_rebuild"] = entry["origin"] in self.component_slugs
                entry["rebuild_count"] = self.rebuild_counts.get(entry["origin"], 0)
            # Add missing ones
            result.extend(
                {
                    "origin": missing,
                    "id__count": 0,
                    "can_rebuild": True,
                    "rebuild_count": self.rebuild_counts.get(missing, 0),
                    "url": get_url(missing),
                }
                for missing in self.component_slugs - existing
            )
        return from_file + result

    def get_languages(self):
        if "manage" in self.kwargs:
            return []
        results = (
            self.entries.values("source_language", "target_language")
            .order_by("source_language__code", "target_language__code")
            .annotate(Count("id"))
        )
        languages = {
            language.id: language
            for language in Language.objects.filter(
                pk__in={result["source_language"] for result in results}
                | {result["target_language"] for result in results}
            )
        }

        return [
            {
                "source_language": languages[result["source_language"]],
                "target_language": languages[result["target_language"]],
                "id__count": result["id__count"],
            }
            for result in results
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.objects)
        status_counts = self.entries.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status=Memory.STATUS_ACTIVE)),
            pending=Count("id", filter=Q(status=Memory.STATUS_PENDING)),
        )
        context["num_entries"] = status_counts["total"]
        context["active_entries"] = status_counts["active"]
        context["pending_entries"] = status_counts["pending"]
        context["entries_origin"] = self.get_origins()
        context["entries_languages"] = self.get_languages()
        context["total_entries"] = Metric.objects.get_current_metric(
            None, Metric.SCOPE_GLOBAL, 0
        )["memory"]
        context["download_url"] = self.get_url("memory-download")
        user = self.request.user
        if check_perm(user, "memory.delete", self.objects):
            context["delete_url"] = self.get_url("memory-delete")
            if {"project", "workspace"} & self.objects.keys():
                context["rebuild_url"] = self.get_url("memory-rebuild")
                context["rebuild_entries_count"] = sum(self.rebuild_counts.values())
        if "workspace" not in self.objects and check_perm(
            user, "memory.edit", self.objects
        ):
            context["upload_url"] = self.get_url("memory-upload")
            context["upload_form"] = UploadForm()
        if "from_file" in self.objects:
            context["menu_items"] = MENU
            context["menu_page"] = "memory"
        if "from_file" in self.objects or (
            "project" in self.objects and self.objects["project"].use_shared_tm
        ):
            context["shared_entries"] = Memory.objects.filter_scope(
                Q(
                    scope=MemoryScope.SCOPE_SHARED,
                    source_project__contribute_shared_tm=True,
                ),
            ).count()
        return context


class DownloadView(MemoryView):
    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        fmt = request.GET.get("format", "json")
        data = (
            Memory.objects.filter_type(**self.objects).prefetch_scopes().prefetch_lang()
        )
        category = get_export_category(self.objects)
        if "origin" in request.GET:
            data = data.filter(origin=request.GET["origin"])
        source_language_id = get_language_filter(request, "source_language")
        if source_language_id is not None:
            data = data.filter(source_language_id=source_language_id)
        target_language_id = get_language_filter(request, "target_language")
        if target_language_id is not None:
            data = data.filter(target_language_id=target_language_id)
        if "from_file" in self.objects and "kind" in request.GET:
            if request.GET["kind"] == "shared":
                data = (
                    Memory.objects.filter_type(use_shared=True)
                    .prefetch_scopes()
                    .prefetch_lang()
                )
                category = CATEGORY_SHARED
            elif request.GET["kind"] == "all":
                data = (
                    Memory.objects.filter_scope(Q()).prefetch_scopes().prefetch_lang()
                )
                category = None
        if fmt == "tmx":
            response = render(
                request,
                "memory/dump.tmx",
                {"data": data},
                content_type="application/x-tmx",
            )
        else:
            fmt = "json"
            if category is None:
                payload = [entry for item in data for entry in item.as_dicts()]
            else:
                payload = [item.as_dict(category=category) for item in data]
            response = JsonResponse(payload, safe=False)
        response["Content-Disposition"] = CD_TEMPLATE.format(fmt)
        return response
