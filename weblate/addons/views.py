# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.views.generic import DetailView, ListView, UpdateView

from weblate.addons.models import ADDONS, Addon
from weblate.auth.decorators import check_management_access
from weblate.trans.models import Category, Change, Component, Project
from weblate.utils import messages
from weblate.utils.views import PathViewMixin, get_paginator

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import AuthenticatedHttpRequest


@dataclass(frozen=True)
class AddonListItem:
    instance: Addon
    inherited: bool
    scope_label: StrOrPromise
    scope_description: str
    manage_url: str
    can_manage: bool
    components_url: str


class AddonList(PathViewMixin, ListView):
    paginate_by = None
    model = Addon
    supported_path_types = (None, Component, Project, Category)
    path_object: Component | Project | Category | None
    request: AuthenticatedHttpRequest

    def get_queryset(self):
        if isinstance(self.path_object, Component):
            if not self.request.user.has_perm("component.edit", self.path_object):
                msg = "Can not edit component"
                raise PermissionDenied(msg)
            self.kwargs["component_obj"] = self.path_object
            return Addon.objects.filter_component(self.path_object)
        if isinstance(self.path_object, Category):
            if not self.request.user.has_perm("project.edit", self.path_object.project):
                msg = "Can not edit project"
                raise PermissionDenied(msg)
            self.kwargs["category_obj"] = self.path_object
            return Addon.objects.filter_category(self.path_object)
        if isinstance(self.path_object, Project):
            if not self.request.user.has_perm("project.edit", self.path_object):
                msg = "Can not edit project"
                raise PermissionDenied(msg)
            self.kwargs["project_obj"] = self.path_object
            return Addon.objects.filter_project(self.path_object)

        check_management_access(self.request, "management.addons")
        return Addon.objects.filter_sitewide()

    def _get_scope_url(self, addon: Addon) -> str:
        target = addon.component or addon.category or addon.project
        if target is None:
            return reverse("manage-addons")
        return reverse("addons", kwargs={"path": target.get_url_path()})

    def _can_manage_addon(self, addon: Addon) -> bool:
        if addon.component:
            return self.request.user.has_perm("component.edit", addon.component)
        if addon.category:
            return self.request.user.has_perm("project.edit", addon.category.project)
        if addon.project:
            return self.request.user.has_perm("project.edit", addon.project)
        return self.request.user.has_perm(
            "management.use"
        ) and self.request.user.has_perm("management.addons")

    @staticmethod
    def _get_scope_rank(addon: Addon, target: Component | Project | Category | None):
        if addon.component:
            if addon.component == target:
                return 0
            return 1
        if addon.category:
            if addon.category == target:
                return 0
            return 2
        if addon.project:
            if addon.project == target:
                return 0
            return 3
        if target is None:
            return 0
        return 4

    @staticmethod
    def _get_scope_description(addon: Addon) -> str:
        if addon.component:
            return str(addon.component)
        if addon.category:
            return str(addon.category)
        if addon.project:
            return str(addon.project)
        return gettext("site-wide add-ons")

    @staticmethod
    def _get_scope_label(
        addon: Addon, target: Component | Project | Category | None
    ) -> StrOrPromise:
        if addon.component:
            if addon.repo_scope:
                return gettext("repository wide")
            return gettext("component")
        if addon.category:
            if isinstance(target, Category) and addon.category != target:
                return gettext("parent category")
            if (
                isinstance(target, Component)
                and addon.category_id != target.category_id
            ):
                return gettext("parent category")
            return gettext("category")
        if addon.project:
            return gettext("project-wide")
        return gettext("site-wide")

    def _get_visible_queryset(self):
        target = self.path_object
        query = Q()
        if isinstance(target, Component):
            query |= Q(component=target)
            query |= Q(project=target.project)
            query |= Q(component__linked_component=target, repo_scope=True)
            if target.linked_component:
                query |= Q(component=target.linked_component, repo_scope=True)
            category = target.category
            while category is not None:
                query |= Q(category=category)
                category = category.category
            query |= Q(
                component__isnull=True, category__isnull=True, project__isnull=True
            )
        elif isinstance(target, Category):
            category = target
            while category is not None:
                query |= Q(category=category)
                category = category.category
            query |= Q(project=target.project)
            query |= Q(
                component__isnull=True, category__isnull=True, project__isnull=True
            )
        elif isinstance(target, Project):
            query |= Q(project=target)
            query |= Q(
                component__isnull=True, category__isnull=True, project__isnull=True
            )
        else:
            query |= Q(
                component__isnull=True, category__isnull=True, project__isnull=True
            )

        return (
            Addon.objects.filter(query)
            .select_related(
                "component",
                "component__project",
                "category",
                "category__project",
                "project",
            )
            .prefetch_related("event_set")
            .distinct()
        )

    def get_visible_items(self) -> list[AddonListItem]:
        target = self.path_object
        items = []
        for addon in sorted(
            self._get_visible_queryset(),
            key=lambda item: (self._get_scope_rank(item, target), item.pk or 0),
        ):
            inherited = (addon.component or addon.category or addon.project) != target
            can_manage = self._can_manage_addon(addon)
            items.append(
                AddonListItem(
                    instance=addon,
                    inherited=inherited,
                    scope_label=self._get_scope_label(addon, target),
                    scope_description=self._get_scope_description(addon),
                    manage_url=self._get_scope_url(addon),
                    can_manage=can_manage,
                    components_url=(
                        reverse("addon-components", kwargs={"pk": addon.pk})
                        if not inherited
                        and can_manage
                        and addon.pk
                        and addon.is_valid
                        and (addon.component_id is None or addon.repo_scope)
                        else ""
                    ),
                )
            )
        return items

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
        local_addons = list(result["object_list"])
        result["local_object_list"] = local_addons
        result["object_list"] = self.get_visible_items()
        result["inherited_addons"] = any(
            item.inherited for item in result["object_list"]
        )
        result["object"] = target
        result["change_actions"] = Change.ACTIONS_ADDON
        if target is None:
            result["last_changes"] = (
                Change.objects.filter(
                    action__in=Change.ACTIONS_ADDON,
                    project__isnull=True,
                    category__isnull=True,
                    component__isnull=True,
                )
                .prefetch_for_render()
                .recent()
            )
        elif isinstance(target, Component):
            result["last_changes"] = (
                target.change_set.filter(action__in=Change.ACTIONS_ADDON)
                .prefetch_for_render()
                .recent(skip_preload="component")
            )
        elif isinstance(target, Category):
            result["last_changes"] = (
                Change.objects.filter(
                    action__in=Change.ACTIONS_ADDON,
                    category=target,
                )
                .prefetch_for_render()
                .recent(skip_preload="category")
            )
        else:
            result["last_changes"] = (
                target.change_set.filter(
                    action__in=Change.ACTIONS_ADDON, component=None
                )
                .prefetch_for_render()
                .recent(skip_preload="project")
            )
        installed = {x.addon_name for x in local_addons}

        component: Component | None = None
        category: Category | None = None
        project: Project | None = None
        if isinstance(target, Component):
            component = target
        elif isinstance(target, Category):
            category = target
        elif isinstance(target, Project):
            project = target

        result["available"] = sorted(
            (
                x(Addon())
                for x in ADDONS.values()
                if x.can_install(
                    component=component, category=category, project=project
                )
                and (x.multiple or x.name not in installed)
            ),
            key=lambda x: x.name,
        )
        if component:
            result["scope"] = "component"
        elif category:
            result["scope"] = "category"
        elif project:
            result["scope"] = "project"
        else:
            result["scope"] = "sitewide"

        return result

    def post(self, request: AuthenticatedHttpRequest, **kwargs):
        obj = self.path_object
        obj_component: Component | None = None
        obj_category: Category | None = None
        obj_project: Project | None = None

        if isinstance(obj, Component):
            obj_component = obj
        elif isinstance(obj, Category):
            obj_category = obj
        elif isinstance(obj, Project):
            obj_project = obj

        name = request.POST.get("name")
        if not name:
            return self.redirect_list(gettext("Invalid add-on name: ”%s”") % name)
        addon = ADDONS.get(name)
        if addon is None:
            return self.redirect_list(gettext("Invalid add-on name: ”%s”") % name)
        installed = {x.addon_name for x in self.get_queryset()}
        if not addon.can_install(
            component=obj_component, category=obj_category, project=obj_project
        ) or (name in installed and not addon.multiple):
            return self.redirect_list(
                gettext("Add-on cannot be installed: ”%s”") % name
            )

        form = addon.get_add_form(
            request.user,
            component=obj_component,
            category=obj_category,
            project=obj_project,
            data=request.POST if "form" in request.POST else None,
        )
        if form is None:
            addon.create(
                component=obj_component,
                category=obj_category,
                project=obj_project,
                acting_user=request.user,
            )
            return self.redirect_list()

        if "form" in request.POST and form.is_valid():
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

    # pylint: disable-next=arguments-differ
    def get_object(self):  # type: ignore[override]
        obj = super().get_object()
        if obj.component and not self.request.user.has_perm(
            "component.edit", obj.component
        ):
            msg = "Can not edit component"
            raise PermissionDenied(msg)
        if obj.category and not self.request.user.has_perm(
            "project.edit", obj.category.project
        ):
            msg = "Can not edit project"
            raise PermissionDenied(msg)
        if obj.project and not self.request.user.has_perm("project.edit", obj.project):
            msg = "Can not edit project"
            raise PermissionDenied(msg)
        if obj.project is None and obj.category is None and obj.component is None:
            check_management_access(self.request, "management.addons")
        return obj


class AddonDetail(BaseAddonView, UpdateView):
    template_name_suffix = "_detail"
    object: Addon

    def get_form(self, form_class=None):
        if not self.object.is_valid:
            return None
        return self.object.addon.get_settings_form(
            self.request.user, **self.get_form_kwargs()
        )

    def _get_target(self):
        return self.object.component or self.object.category or self.object.project

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = self._get_target()
        result["instance"] = self.object
        result["addon"] = self.object.addon if self.object.is_valid else None
        result["addon_name"] = self.object.addon_name
        result["components_url"] = (
            reverse("addon-components", kwargs={"pk": self.object.pk})
            if self.object.is_valid and self.object.component_id is None
            else ""
        )
        return result

    def get_success_url(self):
        target = self._get_target()
        if target is None:
            return reverse("manage-addons")
        return reverse("addons", kwargs={"path": target.get_url_path()})

    def trigger_manual_run(self, request: AuthenticatedHttpRequest):
        if not self.object.can_run_manually:
            messages.error(
                request, gettext("This add-on cannot be triggered manually.")
            )
            return redirect(self.get_success_url())

        self.object.schedule_manual_run()
        messages.success(request, gettext("Add-on run has been scheduled."))
        return redirect(self.get_success_url())

    def post(self, request: AuthenticatedHttpRequest, *args, **kwargs):  # type: ignore[override]
        obj = self.get_object()
        self.object = obj
        obj.acting_user = request.user
        if "delete" in request.POST:
            target = obj.component or obj.category or obj.project
            obj.delete()
            if target is None:
                return redirect(reverse("manage-addons"))
            return redirect(reverse("addons", kwargs={"path": target.get_url_path()}))
        if not obj.is_valid:
            messages.error(
                request, gettext("Invalid add-on name: ”%s”") % obj.addon_name
            )
            return redirect(self.get_success_url())
        if "run" in request.POST:
            return self.trigger_manual_run(request)
        return super().post(request, *args, **kwargs)


class AddonLogs(BaseAddonView):
    template_name_suffix = "_logs"

    def get_context_data(self, **kwargs):
        result = super().get_context_data(**kwargs)
        result["object"] = (
            self.object.component or self.object.category or self.object.project
        )
        result["instance"] = self.object
        result["addon"] = self.object.addon if self.object.is_valid else None
        result["addon_name"] = self.object.addon_name
        result["addon_activity_log"] = get_paginator(
            self.request,
            self.object.get_addon_activity_logs(),
        )
        return result


class AddonComponents(BaseAddonView):
    template_name_suffix = "_components"

    def get_components(self) -> QuerySet[Component]:
        if not self.object.is_valid or (
            self.object.component_id and not self.object.repo_scope
        ):
            raise Http404

        result = self.object.affected_components().filter_access(self.request.user)
        if self.object.category_id or self.object.project_id:
            return result.order().prefetch(alerts=False)
        return result.order_project().prefetch(alerts=False)

    def get_context_data(self, **kwargs):
        if not self.object.is_valid or (
            self.object.component_id and not self.object.repo_scope
        ):
            raise Http404

        result = super().get_context_data(**kwargs)
        result["object"] = (
            self.object.component or self.object.category or self.object.project
        )
        result["instance"] = self.object
        result["addon"] = self.object.addon
        result["addon_name"] = self.object.addon_name
        components = get_paginator(self.request, self.get_components())
        result["components"] = components
        result["component_rows"] = [
            {
                "component": component,
                "compatible": self.object.addon.can_process(component=component),
            }
            for component in components
        ]
        return result
