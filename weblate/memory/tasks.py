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
    from weblate.lang.models import Language
    from weblate.trans.models import Component, Project, Unit


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
                translation__component=component,
                state__gte=STATE_TRANSLATED,
                translation__component__is_glossary=False,
            ).exclude(target="")
            if not component.intermediate:
                units = units.exclude(
                    translation__language_id=component.source_language_id
                )
            for unit in units.prefetch_related("translation", "translation__language"):
                handle_unit_translation_change(unit, None, component, project)


def handle_unit_translation_change(
    unit: Unit,
    user: User | None = None,
    component: Component | None = None,
    project: Project | None = None,
) -> None:
    if component is None:
        component = unit.translation.component
    if project is None:
        project = component.project

    # Do not keep per-user memory for bots
    if user and user.is_bot:
        user = None

    source_language: Language = get_machinery_language(component.source_language)
    target_language: Language = get_machinery_language(unit.translation.language)
    source = unit.source
    target = unit.target
    origin = component.full_slug

    if not is_valid_memory_entry(source=source, target=target):
        return

    update_memory.delay_on_commit(
        source_language_id=source_language.id,
        target_language_id=target_language.id,
        source=source,
        target=target,
        origin=origin,
        add_shared=project.contribute_shared_tm,
        user_id=user.id if user is not None else None,
        project_id=project.id,
    )


@app.task(trail=False)
def update_memory(
    *,
    source_language_id: int,
    target_language_id: int,
    source: str,
    target: str,
    origin: str,
    add_shared: bool,
    user_id: int | None,
    project_id: int,
) -> None:
    add_project = True
    add_user = user_id is not None

    # Check matching entries in memory
    for matching in Memory.objects.filter(
        from_file=False,
        source=source,
        target=target,
        origin=origin,
        source_language_id=source_language_id,
        target_language_id=target_language_id,
    ):
        if (
            matching.user_id is None
            and matching.project_id == project_id
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
            and matching.user_id == user_id
            and matching.project_id is None
            and not matching.shared
        ):
            add_user = False

    to_create = []

    if add_project:
        to_create.append(
            Memory(
                user=None,
                project_id=project_id,
                from_file=False,
                shared=False,
                source=source,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
            )
        )
    if add_shared:
        to_create.append(
            Memory(
                user=None,
                project=None,
                from_file=False,
                shared=True,
                source=source,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
            )
        )
    if add_user:
        to_create.append(
            Memory(
                user_id=user_id,
                project=None,
                from_file=False,
                shared=False,
                source=source,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
            )
        )
    if to_create:
        Memory.objects.bulk_create(to_create)
