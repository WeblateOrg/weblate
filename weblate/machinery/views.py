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

from typing import Dict, Optional

from django.core.exceptions import PermissionDenied
from django.http import (
    Http404,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.views.generic.edit import FormView

from weblate.configuration.models import Setting
from weblate.machinery.base import MachineTranslationError
from weblate.machinery.models import MACHINERY
from weblate.trans.models import Unit
from weblate.utils.errors import report_error
from weblate.utils.views import get_project


class MachineryMixin:
    @cached_property
    def global_settings_dict(self):
        return Setting.objects.get_settings_dict(Setting.CATEGORY_MT)


class MachineryProjectMixin(MachineryMixin):
    def post_setup(self, request, kwargs):
        self.project = get_project(request, kwargs["project"])

    @cached_property
    def settings_dict(self):
        return self.project.machinery_settings


class MachineryGlobalMixin(MachineryMixin):
    @cached_property
    def settings_dict(self):
        return self.global_settings_dict


class MachineryConfiguration:
    def __init__(
        self,
        machinery,
        configuration: Optional[Dict[str, str]],
        sitewide: bool = False,
        project=None,
        is_configured: bool = True,
    ):
        self.machinery = machinery
        self.configuration = configuration
        self.sitewide = sitewide
        self.project = project
        self.is_configured = is_configured

    @property
    def is_enabled(self):
        return self.configuration is not None

    @property
    def id(self):
        return self.machinery.get_identifier()

    @property
    def name(self):
        return self.machinery.name

    @property
    def doc_anchor(self):
        return self.machinery.get_doc_anchor()

    @property
    def has_settings(self):
        return self.machinery.settings_form is not None

    def get_absolute_url(self):
        kwargs = {"machinery": self.id}
        if self.project:
            kwargs["project"] = self.project.slug
        return reverse("machinery-edit", kwargs=kwargs)


class ListMachineryView(TemplateView):
    template_name = "machinery/list.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = None
        self.post_setup(request, kwargs)
        self.configured_services = sorted(
            self.get_configured_services(), key=lambda obj: obj.name
        )
        installed_services = {obj.id for obj in self.configured_services}
        self.available_services = sorted(
            (
                MachineryConfiguration(
                    obj, None, project=self.project, is_configured=False
                )
                for name, obj in MACHINERY.items()
                if name not in installed_services
            ),
            key=lambda obj: obj.name,
        )

    def post_setup(self, request, kwargs):
        return

    def get_configured_services(self):
        for service, configuration in self.settings_dict.items():
            machinery = MACHINERY[service]
            yield MachineryConfiguration(machinery, configuration, project=self.project)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["configured_services"] = self.configured_services
        result["available_services"] = self.available_services
        return result


class ListMachineryGlobalView(MachineryGlobalMixin, ListMachineryView):
    pass


class ListMachineryProjectView(MachineryProjectMixin, ListMachineryView):
    def get_configured_services(self):
        yield from super().get_configured_services()
        project_settings = set(self.settings_dict)
        for service, configuration in self.global_settings_dict.items():
            if service in project_settings:
                continue
            machinery = MACHINERY[service]
            yield MachineryConfiguration(
                machinery, configuration, sitewide=True, project=self.project
            )

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["project"] = self.project
        return result


class EditMachineryView(FormView):
    template_name = "machinery/edit.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.machinery_id = kwargs["machinery"]
        self.machinery = MACHINERY[self.machinery_id]
        self.project = None
        self.post_setup(request, kwargs)

    def get_form_class(self):
        return self.machinery.settings_form

    def get_form_kwargs(self):
        result = super().get_form_kwargs()
        result["machinery"] = self.machinery
        return result

    @cached_property
    def settings_dict(self):
        raise NotImplementedError()

    def post_setup(self, request, kwargs):
        return

    def get_initial(self):
        return self.settings_dict.get(self.machinery_id) or {}

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["machinery_id"] = self.machinery.get_identifier()
        result["machinery_name"] = self.machinery.name
        result["machinery_doc_anchor"] = self.machinery.get_doc_anchor()
        return result

    def install_service(self):
        self.save_settings({})

    def form_valid(self, form):
        self.save_settings(form.cleaned_data)
        return super().form_valid(form)

    def save_settings(self, data):
        raise NotImplementedError()

    def delete_service(self):
        raise NotImplementedError()

    def enable_service(self):
        return

    def get_success_url(self):
        kwargs = {}
        if self.project:
            kwargs["project"] = self.project.slug
        return reverse("machinery-list", kwargs=kwargs)

    def post(self, request, *args, **kwargs):
        if "delete" in request.POST:
            self.delete_service()
            return HttpResponseRedirect(self.get_success_url())

        if "enable" in request.POST:
            self.delete_service()
            return HttpResponseRedirect(self.get_success_url())

        if "install" in request.POST:
            if self.machinery.settings_form is not None:
                return self.get(request, *args, **kwargs)
            self.install_service()
            return HttpResponseRedirect(self.get_success_url())
        return super().post(request, *args, **kwargs)


class EditMachineryGlobalView(MachineryGlobalMixin, EditMachineryView):
    def save_settings(self, data):
        setting, created = Setting.objects.get_or_create(
            category=Setting.CATEGORY_MT,
            name=self.machinery_id,
            defaults={"value": data},
        )
        if not created and setting.value != data:
            setting.value = data
            setting.save()

    def delete_service(self):
        Setting.objects.filter(
            category=Setting.CATEGORY_MT,
            name=self.machinery_id,
        ).delete()

    def form_valid(self, form):
        self.save_settings(form.cleaned_data)
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("machinery.edit"):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)


class EditMachineryProjectView(MachineryProjectMixin, EditMachineryView):
    def save_settings(self, data):
        self.project.machinery_settings[self.machinery_id] = data
        self.project.save(update_fields=["machinery_settings"])

    def delete_service(self):
        if self.machinery_id in self.project.machinery_settings:
            self.enable_service()
        else:
            self.save_settings(None)

    def enable_service(self):
        del self.project.machinery_settings[self.machinery_id]
        self.project.save(update_fields=["machinery_settings"])

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_project(request, kwargs["project"])

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("project.edit", self.project):
            raise PermissionDenied()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["project"] = self.project
        return result


def handle_machinery(request, service, unit, search=None):
    if service not in MACHINERY:
        raise Http404("Invalid service specified")

    translation = unit.translation
    if not request.user.has_perm("machinery.view", translation):
        raise PermissionDenied()

    translation_service_class = MACHINERY[service]

    # Error response
    response = {
        "responseStatus": 500,
        "responseDetails": "",
        "translations": [],
        "lang": translation.language.code,
        "dir": translation.language.direction,
        "service": translation_service_class.name,
    }

    machinery_settings = translation.component.project.get_machinery_settings()

    try:
        translation_service = translation_service_class(machinery_settings[service])
    except KeyError:
        response["responseDetails"] = _("Service is currently not available.")
    else:
        try:
            response["translations"] = translation_service.translate(
                unit, request.user, search=search
            )
            response["responseStatus"] = 200
        except MachineTranslationError as exc:
            response["responseDetails"] = str(exc)
        except Exception as error:
            report_error()
            response["responseDetails"] = f"{error.__class__.__name__}: {error}"

    if response["responseStatus"] != 200:
        translation.log_info("machinery failed: %s", response["responseDetails"])

    return JsonResponse(data=response)


@require_POST
def translate(request, unit_id, service):
    """AJAX handler for translating."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    return handle_machinery(request, service, unit)


@require_POST
def memory(request, unit_id):
    """AJAX handler for translation memory."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    query = request.POST.get("q")
    if not query:
        return HttpResponseBadRequest("Missing search string")

    return handle_machinery(request, "weblate-translation-memory", unit, search=query)
