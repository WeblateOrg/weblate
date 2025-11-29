# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from weblate.checks.flags import Flags
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Unit
from weblate.trans.models.pending import PendingUnitChange
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from weblate.auth.models import User
    from weblate.trans.models import Label, Project
    from weblate.trans.models.unit import UnitQuerySet

EDITABLE_STATES = {
    STATE_FUZZY,
    STATE_NEEDS_REWRITING,
    STATE_NEEDS_CHECKING,
    STATE_TRANSLATED,
    STATE_APPROVED,
}


def bulk_perform(  # noqa: C901
    user: User | None,
    unit_set: UnitQuerySet,
    *,
    query: str,
    target_state: int | str,
    add_flags: str | Flags,
    remove_flags: str | Flags,
    add_labels: QuerySet[Label],
    remove_labels: QuerySet[Label],
    project: Project,
    components: QuerySet[Component] | list[Component] | None = None,
) -> int:
    matching = unit_set.search(query, project=project)
    if components is None:
        components = Component.objects.filter(
            id__in=matching.values_list("translation__component_id", flat=True)
        )

    if isinstance(target_state, str):
        target_state = int(target_state)
    if isinstance(add_flags, str):
        add_flags = Flags(add_flags)
    if isinstance(remove_flags, str):
        remove_flags = Flags(remove_flags)
    add_labels_pks = {label.pk for label in add_labels}
    remove_labels_pks = {label.pk for label in remove_labels}

    update_source = add_flags or remove_flags or add_labels or remove_labels

    updated = 0
    for component in components:
        prev_updated = updated
        component.batch_checks = True
        with transaction.atomic():
            component_units = matching.filter(translation__component=component)

            source_unit_ids = set()

            if target_state == -1:
                # Only fetch source unit ids here
                source_unit_ids = set(
                    component_units.values_list("source_unit_id", flat=True)
                )
            else:
                to_update = []
                source_units = []
                unit_ids = list(component_units.values_list("id", flat=True))
                # Generate changes for state change
                for unit in (
                    Unit.objects.filter(id__in=unit_ids, state__in=EDITABLE_STATES)
                    .exclude(translation__filename="", state=target_state)
                    .prefetch()
                    .select_for_update()
                ):
                    source_unit_ids.add(unit.source_unit_id)

                    if user is None or user.has_perm("unit.edit", unit):
                        # Create change object for edit, update is done outside the loop
                        unit.state = target_state
                        unit.generate_change(
                            user, user, ActionEvents.BULK_EDIT, check_new=False
                        )
                        updated += 1
                        to_update.append(unit)
                        if unit.is_source:
                            source_units.append(unit)

                # Bulk update state
                Unit.objects.filter(pk__in=(unit.pk for unit in to_update)).update(
                    state=target_state
                )
                for unit in to_update:
                    PendingUnitChange.store_unit_change(unit=unit, author=user)
                # Fire source_change event in bulk for source units
                for unit in source_units:
                    # The change is already done in the database, we
                    # need it here to recalculate state of translation
                    # units
                    unit.is_batch_update = True
                    unit.source_unit_save()

            if update_source and (
                user is None or user.has_perm("source.edit", component)
            ):
                # Perform changes on the source units
                source_units = (
                    Unit.objects.filter(pk__in=source_unit_ids)
                    .prefetch()
                    .prefetch_bulk()
                )
                if add_labels or remove_labels:
                    source_units = source_units.prefetch_related("labels")
                for source_unit in source_units.select_for_update():
                    changed = False
                    if add_flags or remove_flags:
                        flags = Flags(source_unit.extra_flags)
                        flags.merge(add_flags)
                        flags.remove(remove_flags)
                        new_flags = flags.format()
                        if source_unit.extra_flags != new_flags:
                            source_unit.is_batch_update = True
                            source_unit.update_extra_flags(new_flags, user)
                            changed = True

                    if add_labels or remove_labels:
                        unit_label_pks = {
                            label.pk for label in source_unit.labels.all()
                        }

                        if add_labels_pks - unit_label_pks:
                            source_unit.is_batch_update = True
                            source_unit.labels.add(*add_labels)
                            changed = True

                        if unit_label_pks & remove_labels_pks:
                            source_unit.is_batch_update = True
                            source_unit.labels.remove(*remove_labels)
                            changed = True

                    if changed:
                        updated += 1

        if prev_updated != updated:
            component.invalidate_cache()
            component.update_source_checks()
            component.run_batched_checks()

    return updated
