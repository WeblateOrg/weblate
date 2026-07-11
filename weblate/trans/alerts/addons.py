# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.utils.translation import gettext_lazy

from weblate.trans.alerts.base import AlertCategory, BaseAlert, MultiAlert
from weblate.trans.alerts.registry import register

if TYPE_CHECKING:
    from weblate.addons.models import Addon
    from weblate.auth.models import User
    from weblate.trans.models.component import Component


class AddonErrorAlert(MultiAlert):
    addon_names: tuple[str, ...] = ()

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        context = super().get_dismissal_context(component, details)
        occurrences = context["details"].get("occurrences")
        if isinstance(occurrences, list):
            context["details"] = {
                **context["details"],
                "occurrences": [
                    {
                        key: value
                        for key, value in occurrence.items()
                        if key != "addon_id"
                    }
                    if isinstance(occurrence, dict)
                    else occurrence
                    for occurrence in occurrences
                ],
            }
        return context

    @classmethod
    def is_relevant_addon(cls, addon: Addon) -> bool:
        return addon.name in cls.addon_names or (
            addon.is_valid and addon.addon.alert == cls.__name__
        )

    def can_user_act(self, user: User, component: Component) -> bool:
        addon_ids = {
            str(occurrence["addon_id"])
            for occurrence in self.occurrences
            if occurrence.get("addon_id") is not None
        }
        addon_names = {
            str(occurrence["addon"])
            for occurrence in self.occurrences
            if occurrence.get("addon") is not None
        }
        addon_names.update(self.addon_names)
        relevant_addons = [
            addon
            for addon in component.addons_cache.addons
            if self.is_relevant_addon(addon)
            and (not addon_ids or str(addon.pk) in addon_ids)
            and (not addon_names or addon.name in addon_names)
        ]

        for addon in relevant_addons:
            if addon.component and user.has_perm("component.edit", addon.component):
                continue
            if addon.category and user.has_perm("project.edit", addon.category.project):
                continue
            if addon.project and user.has_perm("project.edit", addon.project):
                continue
            if (
                addon.component_id is None
                and addon.category_id is None
                and addon.project_id is None
                and user.has_perm("management.addons")
            ):
                continue
            return False
        return bool(relevant_addons)


@register
class AddonScriptError(AddonErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    category = AlertCategory.ADDONS
    doc_page = "admin/addons"


@register
class CDNAddonError(AddonErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    category = AlertCategory.ADDONS
    doc_page = "admin/addons"
    doc_anchor = "addon-weblate-cdn-cdnjs"
    addon_names = ("weblate.cdn.cdnjs",)


@register
class MsgmergeAddonError(AddonErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    category = AlertCategory.ADDONS
    doc_page = "admin/addons"
    doc_anchor = "addon-weblate-gettext-msgmerge"


@register
class ExtractPotAddonError(AddonErrorAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not update POT file.")
    category = AlertCategory.ADDONS
    doc_page = "addons"


@register
class ExtractPotMissingMsgmerge(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("POT updates do not update PO files.")
    category = AlertCategory.ADDONS
    dismissible = True
    doc_page = "addons"
    doc_anchor = "addon-weblate-gettext-msgmerge"
    extractor_addon_names: ClassVar[frozenset[str]] = frozenset(
        {
            "weblate.gettext.xgettext",
            "weblate.gettext.meson",
            "weblate.gettext.django",
            "weblate.gettext.sphinx",
        }
    )
    relevant_addon_names: ClassVar[frozenset[str]] = extractor_addon_names | {
        "weblate.gettext.msgmerge"
    }

    def can_user_act(self, user: User, component: Component) -> bool:
        if super().can_user_act(user, component) or user.has_perm(
            "project.edit", component.project
        ):
            return True
        for addon in component.addons_cache.addons:
            if addon.name not in self.extractor_addon_names:
                continue
            if (
                addon.component_id is None
                and addon.category_id is None
                and addon.project_id is None
                and user.has_perm("management.addons")
            ):
                return True
        return False

    @classmethod
    def get_dismissal_context(cls, component: Component, details: dict) -> dict:
        return {
            "details": details,
            "addons": sorted(
                addon.name
                for addon in component.addons_cache.addons
                if addon.name in cls.relevant_addon_names
            ),
            "file_format": component.file_format,
        }

    @classmethod
    def check_component(cls, component: Component) -> bool | dict | None:
        has_extractor = False
        has_msgmerge = False

        for addon in component.addons_cache.addons:
            if not addon.is_valid:
                continue
            if not addon.addon.can_process(component=component):
                continue
            if addon.name in cls.extractor_addon_names:
                has_extractor = True
            elif addon.name == "weblate.gettext.msgmerge":
                has_msgmerge = True

        return has_extractor and not has_msgmerge
