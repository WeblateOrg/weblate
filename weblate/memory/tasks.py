# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import defaultdict
from operator import itemgetter
from typing import TYPE_CHECKING, TypedDict

from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import MD5

from weblate.machinery.base import get_machinery_language
from weblate.memory.models import Memory
from weblate.memory.utils import is_valid_memory_entry
from weblate.utils.celery import app
from weblate.utils.state import STATE_APPROVED, STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.lang.models import Language
    from weblate.trans.models import Component, Project, Unit

MEMORY_UPDATE_BATCH_SIZE = 1000


class MemoryUpdatePayload(TypedDict):
    source_language_id: int
    target_language_id: int
    source: str
    context: str
    target: str
    origin: str
    add_shared: bool
    add_project: bool
    add_user: bool
    user_id: int | None
    project_id: int
    unit_state: int


type MemoryKey = tuple[str, int, int, str, str]
type MemoryGroupKey = tuple[str, int, int]
type MemoryCategory = tuple[str, int | None]
type MemoryGroupEntry = tuple[int, MemoryKey, MemoryUpdatePayload, int]


@app.task(trail=False)
def import_memory(project_id: int, component_id: int | None = None) -> None:
    from weblate.trans.models import Project, Unit  # noqa: PLC0415

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
    payload = get_unit_memory_update(unit, user, component, project)
    if payload is not None:
        schedule_memory_update(payload)


def get_unit_memory_update(
    unit: Unit,
    user: User | None = None,
    component: Component | None = None,
    project: Project | None = None,
) -> MemoryUpdatePayload | None:
    if component is None:
        component = unit.translation.component
    if project is None:
        project = component.project

    # Do not keep per-user memory for bots
    if user is None or (user and user.is_bot):
        user_id = None
        add_user = False
    else:
        user_id = user.id
        add_user = user.profile.contribute_personal_tm

    source_language: Language = get_machinery_language(component.source_language)
    target_language: Language = get_machinery_language(unit.translation.language)
    source = unit.source
    target = unit.target
    origin = component.full_slug

    if not is_valid_memory_entry(source=source, target=target):
        return None

    return {
        "source_language_id": source_language.id,
        "target_language_id": target_language.id,
        "source": source,
        "target": target,
        "origin": origin,
        "add_shared": project.contribute_shared_tm,
        "user_id": user_id,
        "project_id": project.id,
        "add_project": component.contribute_project_tm,
        "add_user": add_user,
        "unit_state": unit.state,
        "context": unit.context or "",
    }


def schedule_memory_update(payload: MemoryUpdatePayload) -> None:
    update_memory.delay_on_commit(**payload)


def schedule_memory_updates(payloads: list[MemoryUpdatePayload]) -> None:
    for offset in range(0, len(payloads), MEMORY_UPDATE_BATCH_SIZE):
        update_memory_bulk.delay_on_commit(
            payloads[offset : offset + MEMORY_UPDATE_BATCH_SIZE]
        )


def get_memory_status(project: Project, unit_state: int) -> int:
    if (project.translation_review and unit_state == STATE_APPROVED) or (
        not project.translation_review and unit_state >= STATE_TRANSLATED
    ):
        return Memory.STATUS_ACTIVE
    return Memory.STATUS_PENDING


get_memory_key = itemgetter(
    "origin", "source_language_id", "target_language_id", "source", "target"
)


@app.task(trail=False)
def update_memory(
    *,
    source_language_id: int,
    target_language_id: int,
    source: str,
    context: str,
    target: str,
    origin: str,
    add_shared: bool,
    add_project: bool,
    add_user: bool,
    user_id: int | None,
    project_id: int,
    unit_state: int,
) -> None:
    from weblate.trans.models import Project  # noqa: PLC0415

    project = Project.objects.get(pk=project_id)
    check_matching = True
    memory_status = get_memory_status(project, unit_state)
    if memory_status == Memory.STATUS_ACTIVE:
        if project.autoclean_tm:
            # delete old entries, including those with different targets
            Memory.objects.filter(
                from_file=False,
                source=source,
                origin=origin,
                context=context,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
            ).delete()
            check_matching = False
    else:
        memory_status = Memory.STATUS_PENDING
    to_create = []
    to_update = []

    if check_matching:
        # Check matching entries in memory
        for matching in Memory.objects.filter(
            from_file=False,
            source=source,
            target=target,
            origin=origin,
            source_language_id=source_language_id,
            target_language_id=target_language_id,
        ):
            if matching.target == target and matching.status != memory_status:
                matching.status = memory_status
                to_update.append(matching)

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

    if add_project:
        to_create.append(
            Memory(
                user=None,
                project_id=project_id,
                from_file=False,
                shared=False,
                source=source,
                context=context,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
                status=memory_status,
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
                context=context,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
                status=memory_status,
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
                context=context,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
                status=memory_status,
            )
        )

    if to_create:
        Memory.objects.bulk_create(to_create)

    if to_update:
        Memory.objects.bulk_update(to_update, fields=["status"])


def get_memory_category(memory: Memory) -> MemoryCategory | None:
    if memory.user_id is None and memory.project_id is not None and not memory.shared:
        return ("project", memory.project_id)
    if memory.user_id is None and memory.project_id is None and memory.shared:
        return ("shared", None)
    if memory.user_id is not None and memory.project_id is None and not memory.shared:
        return ("user", memory.user_id)
    return None


def get_group_matching_memory(
    group_key: MemoryGroupKey,
    group_entries: list[MemoryGroupEntry],
    statuses: dict[MemoryKey, int],
) -> tuple[dict[MemoryKey, set[MemoryCategory]], list[Memory]]:
    origin, source_language_id, target_language_id = group_key
    expected_keys = {key for _, key, _, _ in group_entries}
    matching_pairs = Q()
    for _, _, _, source, target in expected_keys:
        matching_pairs |= Q(
            source__md5=MD5(Value(source)), target__md5=MD5(Value(target))
        )
    existing = defaultdict(set)
    to_update = []

    for matching in Memory.objects.filter(
        matching_pairs,
        from_file=False,
        origin=origin,
        source_language_id=source_language_id,
        target_language_id=target_language_id,
    ):
        key = (
            matching.origin,
            matching.source_language_id,
            matching.target_language_id,
            matching.source,
            matching.target,
        )
        if key not in expected_keys:
            continue
        if matching.status != statuses[key]:
            matching.status = statuses[key]
            to_update.append(matching)
        category = get_memory_category(matching)
        if category is not None:
            existing[key].add(category)

    return existing, to_update


def create_memory_entry(
    entry: MemoryUpdatePayload, *, status: int, category: str
) -> Memory:
    if category == "project":
        return Memory(
            user=None,
            project_id=entry["project_id"],
            from_file=False,
            shared=False,
            source=entry["source"],
            context=entry["context"],
            target=entry["target"],
            origin=entry["origin"],
            source_language_id=entry["source_language_id"],
            target_language_id=entry["target_language_id"],
            status=status,
        )
    if category == "shared":
        return Memory(
            user=None,
            project=None,
            from_file=False,
            shared=True,
            source=entry["source"],
            context=entry["context"],
            target=entry["target"],
            origin=entry["origin"],
            source_language_id=entry["source_language_id"],
            target_language_id=entry["target_language_id"],
            status=status,
        )
    return Memory(
        user_id=entry["user_id"],
        project=None,
        from_file=False,
        shared=False,
        source=entry["source"],
        context=entry["context"],
        target=entry["target"],
        origin=entry["origin"],
        source_language_id=entry["source_language_id"],
        target_language_id=entry["target_language_id"],
        status=status,
    )


def create_missing_memory_entries(
    group_entries: list[MemoryGroupEntry],
    existing: dict[MemoryKey, set[MemoryCategory]],
) -> list[Memory]:
    result = []
    for _, key, entry, status in sorted(group_entries):
        categories = existing[key]
        if entry["add_project"] and ("project", entry["project_id"]) not in categories:
            result.append(create_memory_entry(entry, status=status, category="project"))
            categories.add(("project", entry["project_id"]))
        if entry["add_shared"] and ("shared", None) not in categories:
            result.append(create_memory_entry(entry, status=status, category="shared"))
            categories.add(("shared", None))
        user_id = entry["user_id"]
        if entry["add_user"] and ("user", user_id) not in categories:
            result.append(create_memory_entry(entry, status=status, category="user"))
            categories.add(("user", user_id))
    return result


@app.task(trail=False)
def update_memory_bulk(entries: list[MemoryUpdatePayload]) -> None:
    from weblate.trans.models import Project  # noqa: PLC0415

    if not entries:
        return

    projects = Project.objects.in_bulk({entry["project_id"] for entry in entries})
    fallback = []
    grouped_entries = defaultdict(list)
    statuses = {}

    for position, entry in enumerate(entries):
        project = projects[entry["project_id"]]
        if project.autoclean_tm:
            fallback.append(entry)
            continue

        status = get_memory_status(project, entry["unit_state"])
        key = get_memory_key(entry)
        grouped_entries[key[:3]].append((position, key, entry, status))
        statuses[key] = status

    for entry in fallback:
        update_memory(**entry)

    to_create = []
    to_update = []

    for group_key, group_entries in grouped_entries.items():
        existing, group_updates = get_group_matching_memory(
            group_key, group_entries, statuses
        )
        to_update.extend(group_updates)
        to_create.extend(create_missing_memory_entries(group_entries, existing))

    if to_create:
        Memory.objects.bulk_create(to_create, batch_size=MEMORY_UPDATE_BATCH_SIZE)

    if to_update:
        Memory.objects.bulk_update(to_update, fields=["status"])
