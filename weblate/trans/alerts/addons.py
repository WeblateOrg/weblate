# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.trans.alerts.base import AlertCategory, BaseAlert, MultiAlert
from weblate.trans.alerts.registry import register

if TYPE_CHECKING:
    from weblate.trans.models.component import Component


@register
class AddonScriptError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    category = AlertCategory.ADDONS
    doc_page = "admin/addons"


@register
class CDNAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    category = AlertCategory.ADDONS
    doc_page = "admin/addons"
    doc_anchor = "addon-weblate-cdn-cdnjs"


@register
class MsgmergeAddonError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not run add-on.")
    category = AlertCategory.ADDONS
    doc_page = "admin/addons"
    doc_anchor = "addon-weblate-gettext-msgmerge"


@register
class ExtractPotAddonError(MultiAlert):
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

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        extractors = {
            "weblate.gettext.xgettext",
            "weblate.gettext.meson",
            "weblate.gettext.django",
            "weblate.gettext.sphinx",
        }
        has_extractor = False
        has_msgmerge = False

        for addon in component.addons_cache.addons:
            if not addon.is_valid:
                continue
            if not addon.addon.can_process(component=component):
                continue
            if addon.name in extractors:
                has_extractor = True
            elif addon.name == "weblate.gettext.msgmerge":
                has_msgmerge = True

        return has_extractor and not has_msgmerge
