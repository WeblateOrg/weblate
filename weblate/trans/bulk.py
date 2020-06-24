#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from weblate.utils.state import STATE_EMPTY, STATE_READONLY


def bulk_perform(
    user,
    unit_set,
    query,
    target_state,
    add_flags,
    remove_flags,
    add_labels,
    remove_labels,
):
    matching = unit_set.search(query)
    components = Component.objects.filter(
        id__in=matching.values_list("translation__component_id", flat=True)
    )

    target_state = int(target_state)
    add_flags = Flags(add_flags)
    remove_flags = Flags(remove_flags)

    updated = 0
    for component in components:
        component.preload_sources()
        component.commit_pending("bulk edit", user)
        with transaction.atomic(), component.lock():
            state_updates = []
            for unit in matching.filter(
                translation__component=component
            ).select_for_update():
                if user is not None and not user.has_perm("unit.edit", unit):
                    continue
                updated += 1
                if (
                    target_state != -1
                    and target_state != unit.state
                    and unit.state > STATE_EMPTY
                    and unit.state < STATE_READONLY
                ):
                    state_updates.append(unit.pk)
                    unit.generate_change(user, user, Change.ACTION_BULK_EDIT)
                if add_flags or remove_flags:
                    flags = Flags(unit.source_info.extra_flags)
                    flags.merge(add_flags)
                    flags.remove(remove_flags)
                    unit.source_info.is_bulk_edit = True
                    unit.source_info.extra_flags = flags.format()
                    unit.source_info.save(update_fields=["extra_flags"])
                if add_labels:
                    unit.source_info.is_bulk_edit = True
                    unit.source_info.labels.add(*add_labels)
                if remove_labels:
                    unit.source_info.is_bulk_edit = True
                    unit.source_info.labels.remove(*remove_labels)

        Unit.objects.filter(pk__in=state_updates).update(
            pending=True, state=target_state
        )
        component.invalidate_stats_deep()

    return updated
