# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Synchronous operations shared by add-ons and declarative automation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils.translation import override

from weblate.machinery.base import MachineTranslationError
from weblate.trans.autotranslate import BatchAutoTranslate
from weblate.trans.bulk import bulk_perform
from weblate.trans.models import Unit

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Component


def automatic_translation(
    component: Component,
    settings: dict[str, Any],
    user: User | None,
    *,
    enforce_permissions: bool = True,
) -> dict[str, Any]:
    auto = BatchAutoTranslate(
        component,
        user=user,
        q=settings["q"],
        mode=settings["mode"],
        component_wide=True,
        enforce_permissions=enforce_permissions,
    )
    message = auto.perform(
        auto_source=settings["auto_source"],
        engines=settings["engines"],
        threshold=settings["threshold"],
        source_component_ids=(
            [settings["component"]] if settings.get("component") else None
        ),
    )
    component.run_batched_checks()
    if auto.failure_message:
        raise MachineTranslationError(auto.failure_message)
    return {
        "component": component.pk,
        "updated": auto.updated,
        "message": message,
        "warnings": auto.get_warnings(),
    }


def bulk_edit(component: Component, settings: dict[str, Any]) -> dict[str, Any]:
    labels = component.project.label_set
    updated = bulk_perform(
        None,
        Unit.objects.filter(translation__component=component),
        components=[component],
        query=settings["q"],
        target_state=settings["state"],
        add_flags=settings["add_flags"],
        remove_flags=settings["remove_flags"],
        add_translation_flags=settings.get("add_translation_flags", ""),
        remove_translation_flags=settings.get("remove_translation_flags", ""),
        add_labels=labels.filter(name__in=settings["add_labels"]),
        remove_labels=labels.filter(name__in=settings["remove_labels"]),
        project=component.project,
    )
    return {"component": component.pk, "updated": updated}


def execute_operation(
    action: dict[str, Any], component: Component, user: User | None
) -> dict[str, Any]:
    # Persisted results must not depend on the worker's active UI language.
    with override("en"):
        if action["action"] == "weblate.automatic_translation":
            result = automatic_translation(
                component, action["settings"], user, enforce_permissions=False
            )
            warnings = result["warnings"]
            result["warnings"] = [str(warning)[:1024] for warning in warnings[:20]]
            result["warnings_omitted"] = max(0, len(warnings) - 20)
            return result
        if action["action"] == "weblate.bulk_edit":
            return bulk_edit(component, action["settings"])
    msg = "Unsupported automation operation"
    raise ValueError(msg)
