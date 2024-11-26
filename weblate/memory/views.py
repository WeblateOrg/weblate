# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.views.generic.base import TemplateView

from weblate.auth.models import AuthenticatedHttpRequest
from weblate.lang.models import Language
from weblate.memory.forms import DeleteForm, UploadForm
from weblate.memory.models import Memory, MemoryImportError
from weblate.memory.tasks import import_memory
from weblate.metrics.models import Metric
from weblate.trans.models import Project
from weblate.utils import messages
from weblate.utils.views import ErrorFormView, parse_path
from weblate.wladmin.views import MENU

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest, User

CD_TEMPLATE = 'attachment; filename="weblate-memory.{}"'


def get_objects(request: AuthenticatedHttpRequest, kwargs):
    if "project" in kwargs:
        return {"project": parse_path(request, [kwargs["project"]], (Project,))}
    if "manage" in kwargs:
        return {"from_file": True}
    return {"user": request.user}


def check_perm(user: User, permission, objects):
    if "project" in objects:
        return user.has_perm(permission, objects["project"])
    if "user" in objects:
        # User can edit own translation memory
        return True
    if "from_file" in objects:
        return user.has_perm(permission)
    return False


@method_decorator(login_required, name="dispatch")
class MemoryFormView(ErrorFormView):
    def get_success_url(self):
        if "manage" in self.kwargs:
            return reverse("manage-memory")
        return reverse("memory", kwargs=self.kwargs)

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):
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
        entries.using("default").delete()
        messages.success(self.request, gettext("Entries were deleted."))
        return super().form_valid(form)


class RebuildView(MemoryFormView):
    form_class = DeleteForm
    request: AuthenticatedHttpRequest

    def form_valid(self, form):
        if (
            not check_perm(self.request.user, "memory.delete", self.objects)
            or "project" not in self.objects
        ):
            raise PermissionDenied
        origin = self.request.POST.get("origin")
        project = self.objects["project"]
        component_id = None
        if origin:
            try:
                component_id = project.component_set.get_by_path(origin).id
            except ObjectDoesNotExist as error:
                raise PermissionDenied from error
        # Delete private entries
        entries = Memory.objects.filter_type(**self.objects)
        if origin:
            entries = entries.filter(origin=origin)
        entries.using("default").delete()
        # Delete possible shared entries
        if origin:
            slugs = [origin]
        else:
            slugs = [
                component.full_slug for component in project.component_set.prefetch()
            ]
        Memory.objects.filter(origin__in=slugs, shared=True).using("default").delete()
        # Rebuild memory in background
        import_memory.delay(project_id=project.id, component_id=component_id)
        messages.success(
            self.request,
            gettext(
                "Entries were deleted and the translation memory will be "
                "rebuilt in the background."
            ),
        )
        return super().form_valid(form)


class UploadView(MemoryFormView):
    form_class = UploadForm
    request: AuthenticatedHttpRequest

    def form_valid(self, form):
        if not check_perm(self.request.user, "memory.edit", self.objects):
            raise PermissionDenied
        try:
            Memory.objects.import_file(
                self.request,
                form.cleaned_data["file"],
                source_language=form.cleaned_data["source_language"],
                target_language=form.cleaned_data["target_language"],
                **self.objects,
            )
            messages.success(
                self.request,
                gettext("File processed, the entries will appear shortly."),
            )
        except MemoryImportError as error:
            messages.error(self.request, str(error))
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class MemoryView(TemplateView):
    template_name = "memory/index.html"
    request: AuthenticatedHttpRequest

    def dispatch(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        self.objects = get_objects(request, kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_url(self, name):
        if "manage" in self.kwargs:
            return reverse(f"manage-{name}")
        return reverse(name, kwargs=self.kwargs)

    @cached_property
    def entries(self):
        return Memory.objects.filter_type(**self.objects)

    def get_origins(self):
        def get_url(slug: str) -> str:
            if "/" not in slug:
                return ""
            return reverse("show", kwargs={"path": slug.split("/")})

        from_file = list(
            self.entries.filter(from_file=True)
            .values("origin")
            .order_by("origin")
            .annotate(Count("id"))
        )
        result = list(
            self.entries.filter(from_file=False)
            .values("origin")
            .order_by("origin")
            .annotate(Count("id"))
        )
        for entry in result:
            entry["url"] = get_url(entry["origin"])
        if "project" in self.objects:
            slugs = {
                component.full_slug
                for component in self.objects["project"].component_set.prefetch()
            }
            existing = {entry["origin"] for entry in result}
            for entry in result:
                entry["can_rebuild"] = entry["origin"] in slugs
            # Add missing ones
            result.extend(
                {
                    "origin": missing,
                    "id__count": 0,
                    "can_rebuild": True,
                    "url": get_url(missing),
                }
                for missing in slugs - existing
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
        context["num_entries"] = self.entries.count()
        context["entries_origin"] = self.get_origins()
        context["entries_languages"] = self.get_languages()
        context["total_entries"] = Metric.objects.get_current_metric(
            None, Metric.SCOPE_GLOBAL, 0
        )["memory"]
        context["upload_url"] = self.get_url("memory-upload")
        context["download_url"] = self.get_url("memory-download")
        user = self.request.user
        if check_perm(user, "memory.delete", self.objects):
            context["delete_url"] = self.get_url("memory-delete")
            if "project" in self.objects:
                context["rebuild_url"] = self.get_url("memory-rebuild")
        if check_perm(user, "memory.edit", self.objects):
            context["upload_form"] = UploadForm()
        if "from_file" in self.objects:
            context["menu_items"] = MENU
            context["menu_page"] = "memory"
        if "from_file" in self.objects or (
            "project" in self.objects and self.objects["project"].use_shared_tm
        ):
            context["shared_entries"] = Memory.objects.filter(shared=True).count()
        return context


class DownloadView(MemoryView):
    def get(self, request: AuthenticatedHttpRequest, *args, **kwargs):
        fmt = request.GET.get("format", "json")
        data = Memory.objects.filter_type(**self.objects).prefetch_lang()
        if "origin" in request.GET:
            data = data.filter(origin=request.GET["origin"])
        if "source_language" in request.GET:
            data = data.filter(source_language_id=request.GET["source_language"])
        if "target_language" in request.GET:
            data = data.filter(target_language_id=request.GET["target_language"])
        if "from_file" in self.objects and "kind" in request.GET:
            if request.GET["kind"] == "shared":
                data = Memory.objects.filter_type(use_shared=True).prefetch_lang()
            elif request.GET["kind"] == "all":
                data = Memory.objects.prefetch_lang()
        if fmt == "tmx":
            response = render(
                request,
                "memory/dump.tmx",
                {"data": data},
                content_type="application/x-tmx",
            )
        else:
            fmt = "json"
            response = JsonResponse([item.as_dict() for item in data], safe=False)
        response["Content-Disposition"] = CD_TEMPLATE.format(fmt)
        return response
