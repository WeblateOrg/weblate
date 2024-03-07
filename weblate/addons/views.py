# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import ListView, UpdateView

from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Component
from weblate.utils import messages
from weblate.utils.views import PathViewMixin


class AddonList(PathViewMixin, ListView):
    paginate_by = None
    model = Addon
    supported_path_types = (Component,)

    def get_queryset(self):
        if not self.request.user.has_perm("component.edit", self.path_object):
            raise PermissionDenied("Can not edit component")
        self.kwargs["component_obj"] = self.path_object
        return Addon.objects.filter_component(self.path_object)

    def get_success_url(self):
        return reverse("addons", kwargs={"path": self.path_object.get_url_path()})

    def redirect_list(self, message=None):
        if message:
            messages.error(self.request, message)
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        component = self.kwargs["component_obj"]
        result["object"] = component
        installed = {x.addon.name for x in result["object_list"]}
        result["available"] = sorted(
            (
                x(Addon())
                for x in ADDONS.values()
                if x.can_install(component, self.request.user)
                and (x.multiple or x.name not in installed)
            ),
            key=lambda x: x.name,
        )
        return result

    def post(self, request, **kwargs):
        component = self.path_object
        component.acting_user = request.user
        name = request.POST.get("name")
        addon = ADDONS.get(name)
        installed = {x.addon.name for x in self.get_queryset()}
        if (
            not name
            or addon is None
            or not addon.can_install(component, request.user)
            or (name in installed and not addon.multiple)
        ):
            return self.redirect_list(gettext("Invalid add-on name: ”%s”") % name)

        form = None
        if addon.settings_form is None:
            addon.create(component)
            return self.redirect_list()
        if "form" in request.POST:
            form = addon.get_add_form(request.user, component, data=request.POST)
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
            form = addon.get_add_form(request.user, component)
        addon.pre_install(component, request)
        return self.response_class(
            request=self.request,
            template=["addons/addon_detail.html"],
            context={
                "addon": addon(Addon()),
                "form": form,
                "object": self.kwargs["component_obj"],
            },
        )


class AddonDetail(UpdateView):
    model = Addon
    template_name_suffix = "_detail"

    def get_form(self, form_class=None):
        return self.object.addon.get_settings_form(
            self.request.user, **self.get_form_kwargs()
        )

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = self.object.component
        result["instance"] = self.object
        result["addon"] = self.object.addon
        return result

    def get_success_url(self):
        return reverse("addons", kwargs={"path": self.object.component.get_url_path()})

    def get_object(self):
        obj = super().get_object()
        if not self.request.user.has_perm("component.edit", obj.component):
            raise PermissionDenied("Can not edit component")
        return obj

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        if "delete" in request.POST:
            obj.component.acting_user = request.user
            obj.delete()
            return redirect(
                reverse("addons", kwargs={"path": obj.component.get_url_path()})
            )
        return super().post(request, *args, **kwargs)
