# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Synchronous operations shared by add-ons and declarative automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.db.models import F, Q

from weblate.machinery.base import MachineTranslationError
from weblate.trans.autotranslate import BatchAutoTranslate
from weblate.trans.bulk import bulk_perform
from weblate.trans.models import Unit

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Component
    from weblate.trans.models.unit import UnitQuerySet


@dataclass
class UnitSelection:
    """Runtime-only unit selection; source edits also select their target units."""

    unit_ids: set[int] | None = None
    source_unit_ids: set[int] = field(default_factory=set)
    expand_source_ids: set[int] = field(default_factory=set)

    def queryset(self, component: Component) -> UnitQuerySet:
        units = Unit.objects.filter(translation__component=component)
        if self.unit_ids is None:
            return units
        selected = Q(pk__in=self.unit_ids)
        if self.expand_source_ids:
            selected |= Q(source_unit_id__in=self.expand_source_ids) & ~Q(
                pk=F("source_unit_id")
            )
        return units.filter(selected)

    def count(self, component: Component) -> int:
        return self.queryset(component).count()


def automatic_translation(
    component: Component,
    settings: dict[str, Any],
    user: User | None,
    *,
    enforce_permissions: bool = True,
    selection: UnitSelection | None = None,
    affected: UnitSelection | None = None,
) -> dict[str, Any]:
    unit_ids = None
    if selection is not None and selection.unit_ids is not None:
        unit_ids = list(
            selection.queryset(component)
            .exclude(pk=F("source_unit_id"))
            .values_list("pk", flat=True)
        )
    auto = BatchAutoTranslate(
        component,
        user=user,
        q=settings["q"],
        mode=settings["mode"],
        component_wide=True,
        enforce_permissions=enforce_permissions,
        unit_ids=unit_ids,
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
    if affected is not None:
        affected.unit_ids = auto.affected_unit_ids
        affected.source_unit_ids = auto.affected_source_unit_ids
    return {
        "component": component.pk,
        "updated": auto.updated,
        "message": message,
        "warnings": auto.get_warnings(),
    }


def bulk_edit(
    component: Component,
    settings: dict[str, Any],
    selection: UnitSelection | None = None,
    affected: UnitSelection | None = None,
) -> dict[str, Any]:
    labels = component.project.label_set
    if selection is None:
        selection = UnitSelection()
    affected_ids: set[int] = set()
    affected_sources: set[int] = set()
    updated = bulk_perform(
        None,
        selection.queryset(component),
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
        affected_unit_ids=affected_ids,
        affected_source_unit_ids=affected_sources,
    )
    if affected is not None:
        affected.unit_ids = affected_ids
        affected.source_unit_ids = affected_sources
        affected.expand_source_ids = affected_ids & affected_sources
    return {"component": component.pk, "updated": updated}
