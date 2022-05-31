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

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic.base import TemplateView

from weblate.memory.forms import DeleteForm, UploadForm
from weblate.memory.models import Memory, MemoryImportError
from weblate.memory.tasks import import_memory
from weblate.metrics.models import Metric
from weblate.utils import messages
from weblate.utils.views import ErrorFormView, get_project
from weblate.wladmin.views import MENU

CD_TEMPLATE = 'attachment; filename="weblate-memory.{}"'


def get_objects(request, kwargs):
    if "project" in kwargs:
        return {"project": get_project(request, kwargs["project"])}
    if "manage" in kwargs:
        return {"from_file": True}
    return {"user": request.user}


def check_perm(user, permission, objects):
    if "project" in objects:
        return user.has_perm(permission, objects["project"])
    if "user" in objects:
        # User can edit own translation memory
        return True
    if "from_file" in objects:
        return user.has_perm("memory.edit")
    return False


@method_decorator(login_required, name="dispatch")
class MemoryFormView(ErrorFormView):
    def get_success_url(self):
        if "manage" in self.kwargs:
            return reverse("manage-memory")
        return reverse("memory", kwargs=self.kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.objects = get_objects(request, kwargs)
        return super().dispatch(request, *args, **kwargs)


class DeleteView(MemoryFormView):

    form_class = DeleteForm

    def form_valid(self, form):
        if not check_perm(self.request.user, "memory.delete", self.objects):
            raise PermissionDenied()
        entries = Memory.objects.filter_type(**self.objects)
        if "origin" in self.request.POST:
            entries = entries.filter(origin=self.request.POST["origin"])
        entries.delete()
        messages.success(self.request, _("Entries deleted."))
        return super().form_valid(form)


class RebuildView(MemoryFormView):

    form_class = DeleteForm

    def form_valid(self, form):
        if (
            not check_perm(self.request.user, "memory.delete", self.objects)
            or "project" not in self.objects
        ):
            raise PermissionDenied()
        origin = self.request.POST.get("origin")
        project = self.objects["project"]
        component_id = None
        if origin:
            try:
                component_id = project.component_set.get(
                    slug=origin.split("/", 1)[-1]
                ).id
            except ObjectDoesNotExist:
                raise PermissionDenied()
        # Delete private entries
        entries = Memory.objects.filter_type(**self.objects)
        if origin:
            entries = entries.filter(origin=origin)
        entries.delete()
        # Delete possible shared entries
        if origin:
            slugs = [origin]
        else:
            slugs = [component.full_slug for component in project.component_set.all()]
        Memory.objects.filter(origin__in=slugs, shared=True).delete()
        # Rebuild memory in background
        import_memory.delay(project_id=project.id, component_id=component_id)
        messages.success(
            self.request,
            _("Entries deleted and memory will be rebuilt in the background."),
        )
        return super().form_valid(form)


class UploadView(MemoryFormView):
    form_class = UploadForm

    def form_valid(self, form):
        if not check_perm(self.request.user, "memory.edit", self.objects):
            raise PermissionDenied()
        try:
            Memory.objects.import_file(
                self.request, form.cleaned_data["file"], **self.objects
            )
            messages.success(
                self.request, _("File processed, the entries will appear shortly.")
            )
        except MemoryImportError as error:
            messages.error(self.request, str(error))  # noqa: G200
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class MemoryView(TemplateView):
    template_name = "memory/index.html"

    def dispatch(self, request, *args, **kwargs):
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
        result = list(
            self.entries.values("origin").order_by("origin").annotate(Count("id"))
        )
        if "project" in self.objects:
            slugs = {
                component.full_slug
                for component in self.objects["project"].component_set.all()
            }
            existing = {entry["origin"] for entry in result}
            for entry in result:
                entry["can_rebuild"] = entry["origin"] in slugs
            # Add missing ones
            for missing in slugs - existing:
                result.append({"origin": missing, "id__count": 0, "can_rebuild": True})
        return result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.objects)
        context["num_entries"] = self.entries.count()
        context["entries_origin"] = self.get_origins()
        context["total_entries"] = Metric.objects.get_current(
            None, Metric.SCOPE_GLOBAL, 0, name="memory"
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
    def get(self, request, *args, **kwargs):
        fmt = request.GET.get("format", "json")
        data = Memory.objects.filter_type(**self.objects).prefetch_lang()
        if "origin" in request.GET:
            data = data.filter(origin=request.GET["origin"])
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
