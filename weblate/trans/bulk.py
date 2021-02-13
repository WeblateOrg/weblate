#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from django.db import transaction

from weblate.checks.flags import Flags
from weblate.trans.models import Change, Component, Unit
from weblate.utils.db import get_nokey_args
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, STATE_TRANSLATED

EDITABLE_STATES = STATE_FUZZY, STATE_TRANSLATED, STATE_APPROVED


def bulk_perform(
    user,
    unit_set,
    query,
    target_state,
    add_flags,
    remove_flags,
    add_labels,
    remove_labels,
    project,
):
    matching = unit_set.search(query, project=project).prefetch()
    components = Component.objects.filter(
        id__in=matching.values_list("translation__component_id", flat=True)
    )

    target_state = int(target_state)
    add_flags = Flags(add_flags)
    remove_flags = Flags(remove_flags)

    updated = 0
    for component in components:
        with transaction.atomic(), component.lock():
            component.preload_sources()
            component.commit_pending("bulk edit", user)
            component_units = matching.filter(
                translation__component=component
            ).select_for_update(**get_nokey_args())

            can_edit_source = user is None or user.has_perm("source.edit", component)

            update_unit_ids = []
            source_units = []

            for unit in component_units:
                changed = False
                source_unit = unit.source_unit

                if (
                    target_state != -1
                    and (user is None or user.has_perm("unit.edit", unit))
                    and target_state != unit.state
                    and unit.state in EDITABLE_STATES
                ):
                    # Create change object for edit, update is done outside the looop
                    unit.generate_change(
                        user, user, Change.ACTION_BULK_EDIT, check_new=False
                    )
                    changed = True
                    update_unit_ids.append(unit.pk)
                    if unit.is_source:
                        source_units.append(unit)

                if can_edit_source:
                    if add_flags or remove_flags:
                        flags = Flags(source_unit.extra_flags)
                        flags.merge(add_flags)
                        flags.remove(remove_flags)
                        new_flags = flags.format()
                        if source_unit.extra_flags != new_flags:
                            source_unit.is_bulk_edit = True
                            source_unit.extra_flags = new_flags
                            source_unit.save(update_fields=["extra_flags"])
                            changed = True

                    if add_labels:
                        source_unit.is_bulk_edit = True
                        source_unit.labels.add(*add_labels)
                        changed = True

                    if remove_labels:
                        source_unit.is_bulk_edit = True
                        source_unit.labels.remove(*remove_labels)
                        changed = True

                if changed:
                    updated += 1

            if target_state != -1:
                # Bulk update state
                Unit.objects.filter(pk__in=update_unit_ids).update(
                    pending=True, state=target_state
                )
                # Fire source_change event in bulk for source units
                for unit in source_units:
                    # The change is already done in the database, we
                    # need it here to recalculate state of translation
                    # units
                    unit.is_bulk_edit = True
                    unit.pending = True
                    unit.state = target_state
                    unit.source_unit_save()

        component.invalidate_cache()

    return updated
