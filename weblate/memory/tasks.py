# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from weblate.machinery.base import get_machinery_language
from weblate.memory.models import Memory
from weblate.memory.utils import is_valid_memory_entry
from weblate.utils.celery import app
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.auth.models import User


@app.task(trail=False)
def import_memory(project_id: int, component_id: int | None = None) -> None:
    from weblate.trans.models import Project, Unit

    project = Project.objects.get(pk=project_id)

    components = project.component_set.prefetch()
    if component_id:
        components = components.filter(id=component_id)

    for component in components:
        component.log_info("updating translation memory")
        with transaction.atomic():
            units = Unit.objects.filter(
                translation__component=component, state__gte=STATE_TRANSLATED
            ).exclude(target="")
            if not component.intermediate:
                units = units.exclude(
                    translation__language_id=component.source_language_id
                )
            for unit in units.prefetch_related("translation", "translation__language"):
                update_memory(None, unit, component, project)


@app.task(trail=False)
def handle_unit_translation_change(unit_id, user_id=None) -> None:
    from weblate.auth.models import User
    from weblate.trans.models import Unit

    user = None if user_id is None else User.objects.get(pk=user_id)
    try:
        unit = Unit.objects.prefetch().get(pk=unit_id)
    except Unit.DoesNotExist:
        # Unit was removed meanwhile
        return
    update_memory(user, unit)


def update_memory(user: User, unit, component=None, project=None) -> None:
    component = component or unit.translation.component
    project = project or component.project
    params = {
        "source_language": get_machinery_language(component.source_language),
        "target_language": get_machinery_language(unit.translation.language),
        "source": unit.source,
        "target": unit.target,
        "origin": component.full_slug,
    }

    if not is_valid_memory_entry(**params):
        return

    add_project = True
    add_shared = project.contribute_shared_tm
    add_user = user is not None and not user.is_bot

    # Check matching entries in memory
    for matching in Memory.objects.filter(from_file=False, **params):
        if (
            matching.user_id is None
            and matching.project_id == project.id
            and not matching.shared
        ):
            add_project = False
        elif (
            add_shared
            and matching.user_id is None
            and matching.project_id is None
            and matching.shared
        ):
            add_shared = False
        elif (
            add_user
            and matching.user_id == user.id
            and matching.project_id is None
            and not matching.shared
        ):
            add_user = False

    to_create = []

    if add_project:
        to_create.append(
            Memory(user=None, project=project, from_file=False, shared=False, **params)
        )
    if add_shared:
        to_create.append(
            Memory(user=None, project=None, from_file=False, shared=True, **params)
        )
    if add_user:
        to_create.append(
            Memory(user=user, project=None, from_file=False, shared=False, **params)
        )
    if to_create:
        Memory.objects.bulk_create(to_create)
