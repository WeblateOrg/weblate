# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import transaction

from weblate.checks.flags import Flags
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, Unit
from weblate.trans.models.label import TRANSLATION_LABELS
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, STATE_TRANSLATED

EDITABLE_STATES = {STATE_FUZZY, STATE_TRANSLATED, STATE_APPROVED}


def bulk_perform(  # noqa: C901
    user,
    unit_set,
    *,
    query,
    target_state,
    add_flags,
    remove_flags,
    add_labels,
    remove_labels,
    project,
    components=None,
):
    matching = unit_set.search(query, project=project)
    if components is None:
        components = Component.objects.filter(
            id__in=matching.values_list("translation__component_id", flat=True)
        )

    target_state = int(target_state)
    add_flags = Flags(add_flags)
    remove_flags = Flags(remove_flags)
    add_labels_pks = {label.pk for label in add_labels}
    remove_labels_pks = {label.pk for label in remove_labels}

    update_source = add_flags or remove_flags or add_labels or remove_labels

    updated = 0
    for component in components:
        prev_updated = updated
        component.batch_checks = True
        with transaction.atomic(), component.lock:
            component.commit_pending("bulk edit", user)
            component_units = matching.filter(translation__component=component)

            source_unit_ids = set()

            if target_state == -1:
                # Only fetch source unit ids here
                source_unit_ids = set(
                    component_units.values_list("source_unit_id", flat=True)
                )
            else:
                update_unit_ids = []
                source_units = []
                unit_ids = list(component_units.values_list("id", flat=True))
                # Generate changes for state change
                for unit in (
                    Unit.objects.filter(id__in=unit_ids).prefetch().select_for_update()
                ):
                    source_unit_ids.add(unit.source_unit_id)

                    if (
                        (user is None or user.has_perm("unit.edit", unit))
                        and target_state != unit.state
                        and unit.state in EDITABLE_STATES
                    ):
                        # Create change object for edit, update is done outside the loop
                        unit.generate_change(
                            user, user, ActionEvents.BULK_EDIT, check_new=False
                        )
                        updated += 1
                        update_unit_ids.append(unit.pk)
                        if unit.is_source:
                            source_units.append(unit)

                # Bulk update state
                Unit.objects.filter(pk__in=update_unit_ids).update(
                    pending=True, state=target_state
                )
                # Fire source_change event in bulk for source units
                for unit in source_units:
                    # The change is already done in the database, we
                    # need it here to recalculate state of translation
                    # units
                    unit.is_batch_update = True
                    unit.pending = True
                    unit.state = target_state
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
                            source_unit.extra_flags = new_flags
                            source_unit.save(update_fields=["extra_flags"])
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

            # Handle translation labels
            translation_labels = [
                label for label in remove_labels if label.name in TRANSLATION_LABELS
            ]
            if translation_labels:
                for unit in component_units.filter(labels__in=translation_labels):
                    unit.labels.remove(*translation_labels)
                    updated += 1

        if prev_updated != updated:
            component.invalidate_cache()
            component.update_source_checks()
            component.run_batched_checks()

    return updated
