# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import DetailView, ListView, UpdateView

from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Change, Component, Project
from weblate.utils import messages
from weblate.utils.views import PathViewMixin, get_paginator

if TYPE_CHECKING:
    from weblate.addons.base import BaseAddon
    from weblate.auth.models import AuthenticatedHttpRequest


class AddonList(PathViewMixin, ListView):
    paginate_by = None
    model = Addon
    supported_path_types = (None, Component, Project)
    path_object: Component | Project | None
    request: AuthenticatedHttpRequest

    def get_queryset(self):
        if isinstance(self.path_object, Component):
            if not self.request.user.has_perm("component.edit", self.path_object):
                msg = "Can not edit component"
                raise PermissionDenied(msg)
            self.kwargs["component_obj"] = self.path_object
            return Addon.objects.filter_component(self.path_object)
        if isinstance(self.path_object, Project):
            if not self.request.user.has_perm("project.edit", self.path_object):
                msg = "Can not edit project"
                raise PermissionDenied(msg)
            self.kwargs["project_obj"] = self.path_object
            return Addon.objects.filter_project(self.path_object)

        if not self.request.user.has_perm("management.addons"):
            msg = "Can not manage add-ons"
            raise PermissionDenied(msg)
        return Addon.objects.filter_sitewide()

    def get_success_url(self):
        if self.path_object is None:
            return reverse("manage-addons")
        return reverse("addons", kwargs={"path": self.path_object.get_url_path()})

    def redirect_list(self, message=None):
        if message:
            messages.error(self.request, message)
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        target = self.path_object
        result["object"] = target
        result["change_actions"] = Change.ACTIONS_ADDON
        if target is None:
            result["last_changes"] = Change.objects.filter(
                action__in=Change.ACTIONS_ADDON
            ).order()[:10]
        elif isinstance(target, Component):
            result["last_changes"] = target.change_set.filter(
                action__in=Change.ACTIONS_ADDON
            ).order()[:10]
        else:
            result["last_changes"] = target.change_set.filter(
                action__in=Change.ACTIONS_ADDON, component=None
            ).order()[:10]
        installed = {x.addon.name for x in result["object_list"]}

        if isinstance(target, Component):
            result["available"] = sorted(
                (
                    x(Addon())
                    for x in ADDONS.values()
                    if x.can_install(target, self.request.user)
                    and (x.multiple or x.name not in installed)
                ),
                key=lambda x: x.name,
            )
            result["scope"] = "component"
            result["project_addons"] = Addon.objects.filter_project(
                target.project
            ).count()
        else:
            # This covers both project-wide and site-wide
            result["available"] = sorted(
                (
                    x(Addon())
                    for x in ADDONS.values()
                    if (x.multiple or x.name not in installed)
                ),
                key=lambda x: x.name,
            )
            result["scope"] = "sitewide" if target is None else "project"

        if target is not None:
            result["sitewide_addons"] = Addon.objects.filter_sitewide().count()

        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        obj = self.path_object
        obj_component, obj_project = None, None

        if isinstance(obj, Component):
            obj_component = obj
        elif isinstance(obj, Project):
            obj_project = obj

        name = request.POST.get("name")
        addon: type[BaseAddon] = ADDONS.get(name)
        installed = {x.addon.name for x in self.get_queryset()}
        if (
            not name
            or addon is None
            or (obj_component and not addon.can_install(obj_component, request.user))
            or (name in installed and not addon.multiple)
        ):
            return self.redirect_list(gettext("Invalid add-on name: ”%s”") % name)

        form = None
        if addon.settings_form is None:
            addon.create(component=obj_component, project=obj_project)
            return self.redirect_list()

        if "form" in request.POST:
            form = addon.get_add_form(
                request.user,
                component=obj_component,
                project=obj_project,
                data=request.POST,
            )
            if form.is_valid():
                instance = form.save()
                if addon.stay_on_create:
                    messages.info(
                        self.request,
                        gettext(
                            "Add-on installed, please review integration instructions."
                        ),
                    )
                    return redirect(instance)
                return self.redirect_list()
        else:
            form = addon.get_add_form(
                request.user, component=obj_component, project=obj_project
            )

        addon.pre_install(obj, request)
        return self.response_class(
            request=self.request,
            template=["addons/addon_detail.html"],
            context={
                "addon": addon(Addon()),
                "form": form,
                "object": self.path_object,
            },
        )


class BaseAddonView(DetailView):
    model = Addon
    request: AuthenticatedHttpRequest

    def get_object(self):  # type: ignore[override]
        obj = super().get_object()
        if obj.component and not self.request.user.has_perm(
            "component.edit", obj.component
        ):
            msg = "Can not edit component"
            raise PermissionDenied(msg)
        if obj.project and not self.request.user.has_perm("project.edit", obj.project):
            msg = "Can not edit project"
            raise PermissionDenied(msg)
        if (
            obj.project is None
            and obj.component is None
            and not self.request.user.has_perm("management.addons")
        ):
            msg = "Can not manage add-ons"
            raise PermissionDenied(msg)
        return obj


class AddonDetail(BaseAddonView, UpdateView):
    template_name_suffix = "_detail"
    object: Addon

    def get_form(self, form_class=None):
        return self.object.addon.get_settings_form(
            self.request.user, **self.get_form_kwargs()
        )

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        if self.object.project:
            result["object"] = self.object.project
        else:
            result["object"] = self.object.component
        result["instance"] = self.object
        result["addon"] = self.object.addon
        return result

    def get_success_url(self):
        target = self.object.component or self.object.project
        if target is None:
            return reverse("manage-addons")
        return reverse("addons", kwargs={"path": target.get_url_path()})

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        obj = self.get_object()
        obj.acting_user = request.user
        if "delete" in request.POST:
            target = obj.component or obj.project
            obj.delete()
            if target is None:
                return redirect(reverse("manage-addons"))
            return redirect(reverse("addons", kwargs={"path": target.get_url_path()}))
        return super().post(request, *args, **kwargs)


class AddonLogs(BaseAddonView):
    template_name_suffix = "_logs"

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        if self.object.project:
            result["object"] = self.object.project
        else:
            result["object"] = self.object.component
        result["instance"] = self.object
        result["addon"] = self.object.addon
        result["addon_activity_log"] = get_paginator(
            self.request,
            self.object.get_addon_activity_logs(),
        )
        return result
