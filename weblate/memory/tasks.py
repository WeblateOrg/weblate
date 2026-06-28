# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import defaultdict
from operator import itemgetter
from typing import TYPE_CHECKING, TypedDict
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Min, Q, Value
from django.db.models.functions import MD5
from django.utils import timezone

from weblate.machinery.base import get_machinery_language
from weblate.memory.models import Memory, MemoryScope, MemoryScopeMigrationState
from weblate.memory.utils import is_valid_memory_entry
from weblate.utils.celery import app
from weblate.utils.state import STATE_APPROVED, STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.lang.models import Language
    from weblate.trans.models import Component, Project, Unit

MEMORY_UPDATE_BATCH_SIZE = 1000
MEMORY_UPDATE_LOOKUP_CHUNK_SIZE = 50
MEMORY_SCOPE_BACKFILL_STALE_SECONDS = 15 * 60


class MemoryUpdatePayload(TypedDict):
    source_language_id: int
    target_language_id: int
    source: str
    context: str
    target: str
    origin: str
    add_shared: bool
    add_workspace: bool
    add_project: bool
    add_user: bool
    user_id: int | None
    workspace_id: UUID | None
    project_id: int
    unit_state: int


type MemoryKey = tuple[str, int, int, str, str]
type MemoryGroupKey = tuple[str, int, int]
type MemoryCategory = tuple[str, int | None] | tuple[str, UUID | None, int | None]
type MemoryGroupEntry = tuple[int, MemoryKey, MemoryUpdatePayload, int]
type MemoryScopeKey = tuple[int, int | None, UUID | None, int | None, int | None]
AUTOMATIC_SCOPE_TYPES = (
    MemoryScope.SCOPE_PROJECT,
    MemoryScope.SCOPE_SHARED,
    MemoryScope.SCOPE_USER,
    MemoryScope.SCOPE_WORKSPACE,
)
FILE_SCOPE_TYPES = (
    MemoryScope.SCOPE_GLOBAL_FILE,
    MemoryScope.SCOPE_PROJECT_FILE,
    MemoryScope.SCOPE_USER_FILE,
)


@app.task(trail=False)
def import_memory(project_id: int, component_id: int | None = None) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Project, Unit

    project = Project.objects.select_related("workspace").get(pk=project_id)

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
        "add_workspace": project.effective_contribute_workspace_tm,
        "user_id": user_id,
        "workspace_id": project.workspace_id,
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


def infer_scope_source_project_ids(memories: list[Memory]) -> dict[int, int]:
    # TODO(2028.1): Remove this legacy source-project inference once Weblate no
    # longer supports direct upgrades from 2026 releases. Runtime visibility is
    # scope-only; this exists for the temporary migration/backfill window.
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Change, Project

    project_slugs = {
        memory.origin.split("/", 1)[0] for memory in memories if "/" in memory.origin
    }
    projects = Project.objects.in_bulk(project_slugs, field_name="slug")
    renamed_projects = {
        slug: project
        for slug in project_slugs - projects.keys()
        if (project := Change.objects.lookup_project_rename(slug)) is not None
    }

    result = {}
    for memory in memories:
        if memory.legacy_project_id is not None:
            result[memory.id] = memory.legacy_project_id
            continue
        slug = memory.origin.split("/", 1)[0] if "/" in memory.origin else ""
        project = projects.get(slug) or renamed_projects.get(slug)
        if project is not None:
            result[memory.id] = project.id
    return result


def set_scope_source_project_ids(memories: list[Memory]) -> None:
    source_project_ids = infer_scope_source_project_ids(memories)
    for memory in memories:
        memory.scope_source_project_id = source_project_ids.get(memory.id)


@app.task(trail=False)
def backfill_memory_scopes(batch_size: int = 5000) -> None:
    # TODO(2028.1): Remove this background TM scope backfill once Weblate no
    # longer supports direct upgrades from 2026 releases.
    with transaction.atomic():
        state, _created = (
            MemoryScopeMigrationState.objects.select_for_update().get_or_create(
                name="memory-scope-backfill"
            )
        )
        if state.completed:
            return

        memories = list(
            Memory.objects.filter(id__gt=state.last_memory_id)
            .order_by("id")
            .select_related(
                "legacy_project",
                "legacy_user",
            )[:batch_size]
        )
        if not memories:
            state.completed = True
            state.updated = timezone.now()
            state.save(update_fields=["completed", "updated"])
            run_compact = True
            run_next = False
        else:
            set_scope_source_project_ids(memories)
            MemoryScope.objects.bulk_create_for_memories(memories)
            state.last_memory_id = memories[-1].id
            state.updated = timezone.now()

            if len(memories) == batch_size:
                state.save(update_fields=["last_memory_id", "updated"])
                run_next = True
                run_compact = False
            else:
                state.completed = True
                state.save(update_fields=["last_memory_id", "completed", "updated"])
                run_next = False
                run_compact = True

    if run_next:
        backfill_memory_scopes.delay(batch_size=batch_size)
    elif run_compact:
        compact_memory_scopes.delay()


@app.task(trail=False)
def resume_memory_scope_backfill() -> None:
    # TODO(2028.1): Remove this background TM scope backfill once Weblate no
    # longer supports direct upgrades from 2026 releases.
    state = MemoryScopeMigrationState.objects.filter(
        name="memory-scope-backfill", completed=False
    ).first()
    if state is None:
        needs_backfill = (
            Memory.objects.alias(memory_has_scope=Memory.objects.get_has_scope_exists())
            .filter(memory_has_scope=False)
            .exists()
        )
        if needs_backfill:
            backfill_memory_scopes.delay()
        return

    stale_before = timezone.now() - timezone.timedelta(
        seconds=MEMORY_SCOPE_BACKFILL_STALE_SECONDS
    )
    if state.updated <= stale_before:
        backfill_memory_scopes.delay()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        MEMORY_SCOPE_BACKFILL_STALE_SECONDS,
        resume_memory_scope_backfill.s(),
        name="resume-memory-scope-backfill",
    )


@app.task(trail=False)
def update_memory(  # noqa: PLR0913
    *,
    source_language_id: int,
    target_language_id: int,
    source: str,
    context: str,
    target: str,
    origin: str,
    add_shared: bool,
    add_workspace: bool,
    add_project: bool,
    add_user: bool,
    user_id: int | None,
    workspace_id: UUID | None,
    project_id: int,
    unit_state: int,
) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Project

    project = Project.objects.select_related("workspace").get(pk=project_id)
    memory_objects = Memory.objects.using("default")
    memory_scope_objects = MemoryScope.objects.db_manager("default")
    check_matching = True
    memory_status = get_memory_status(project, unit_state)
    if memory_status == Memory.STATUS_ACTIVE:
        if project.autoclean_tm:
            # delete old entries, including those with different targets
            matching_memory = memory_objects.filter(
                source=source,
                origin=origin,
                context=context,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
            )
            matching_memory.alias(
                memory_has_scope=matching_memory.get_has_scope_exists()
            ).filter(memory_has_scope=False, legacy_from_file=False).delete()
            matching_memory.delete_scope(
                Q(scope__in=AUTOMATIC_SCOPE_TYPES), delete_legacy=False
            )
            check_matching = False
    else:
        memory_status = Memory.STATUS_PENDING
    to_create = []
    to_update: list[Memory] = []

    if check_matching:
        # Check matching entries in memory
        for matching in (
            memory_objects.filter(
                source=source,
                target=target,
                origin=origin,
                source_language_id=source_language_id,
                target_language_id=target_language_id,
            )
            .filter_scope(Q(scope__in=AUTOMATIC_SCOPE_TYPES))
            .prefetch_related("scopes")
        ):
            matching = collect_status_update(matching, memory_status, to_update)

            categories = get_memory_categories(matching)
            if ("project", project_id) in categories:
                add_project = False
            if add_shared and ("shared", project_id) in categories:
                add_shared = False
            if add_user and ("user", user_id) in categories:
                add_user = False
            if add_workspace and ("workspace", workspace_id, project_id) in categories:
                add_workspace = False

    if add_project:
        memory = Memory(
            source=source,
            context=context,
            target=target,
            origin=origin,
            source_language_id=source_language_id,
            target_language_id=target_language_id,
            status=memory_status,
        )
        memory.pending_scopes = [
            MemoryScope(scope=MemoryScope.SCOPE_PROJECT, project_id=project_id)
        ]
        to_create.append(memory)
    if add_shared:
        memory = Memory(
            source=source,
            context=context,
            target=target,
            origin=origin,
            source_language_id=source_language_id,
            target_language_id=target_language_id,
            status=memory_status,
        )
        memory.pending_scopes = [
            MemoryScope(scope=MemoryScope.SCOPE_SHARED, source_project_id=project_id)
        ]
        to_create.append(memory)
    if add_user:
        memory = Memory(
            source=source,
            context=context,
            target=target,
            origin=origin,
            source_language_id=source_language_id,
            target_language_id=target_language_id,
            status=memory_status,
        )
        memory.pending_scopes = [
            MemoryScope(scope=MemoryScope.SCOPE_USER, user_id=user_id)
        ]
        to_create.append(memory)
    if add_workspace and workspace_id is not None:
        memory = Memory(
            source=source,
            context=context,
            target=target,
            origin=origin,
            source_language_id=source_language_id,
            target_language_id=target_language_id,
            status=memory_status,
        )
        memory.pending_scopes = [
            MemoryScope(
                scope=MemoryScope.SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                source_project_id=project_id,
            )
        ]
        to_create.append(memory)

    if to_create:
        with transaction.atomic(using="default"):
            memory_objects.bulk_create(to_create)
            memory_scope_objects.bulk_create_for_memories(to_create)

    if to_update:
        memory_objects.bulk_update(to_update, fields=["status"])


@app.task(trail=False)
def compact_memory_scopes(batch_size: int = 100) -> None:
    # TODO(2028.1): Remove this background TM scope compaction once Weblate no
    # longer supports direct upgrades from 2026 releases.
    state = MemoryScopeMigrationState.objects.filter(
        name="memory-scope-backfill"
    ).first()
    if state is not None and not state.completed:
        backfill_memory_scopes.delay()
        return

    duplicate_groups = list(
        Memory.objects.values(
            "source_language_id",
            "target_language_id",
            "source",
            "target",
            "origin",
            "context",
            "status",
            "legacy_from_file",
        )
        .annotate(first_id=Min("id"), count=Count("id"))
        .filter(count__gt=1)
        .order_by("first_id")[:batch_size]
    )
    if not duplicate_groups:
        return

    for group in duplicate_groups:
        filters = {
            key: group[key]
            for key in (
                "source_language_id",
                "target_language_id",
                "source",
                "target",
                "origin",
                "context",
                "status",
                "legacy_from_file",
            )
        }
        memories = list(
            Memory.objects.filter(**filters)
            .order_by("id")
            .select_related(
                "legacy_project",
                "legacy_user",
            )
        )
        if len(memories) < 2:
            continue
        set_scope_source_project_ids(memories)
        MemoryScope.objects.bulk_create_for_memories(memories)
        memories = list(
            Memory.objects.filter(id__in=[memory.id for memory in memories])
            .order_by("id")
            .prefetch_related("scopes")
        )
        survivor = memories[0]
        duplicate_ids = [memory.id for memory in memories[1:]]
        scope_keys = {
            get_memory_scope_key(scope)
            for memory in memories
            for scope in memory.scopes.all()
        }
        scopes = []
        for memory in memories[1:]:
            scopes.extend(
                [
                    MemoryScope(
                        memory=survivor,
                        scope=scope.scope,
                        project_id=scope.project_id,
                        workspace_id=scope.workspace_id,
                        source_project_id=scope.source_project_id,
                        user_id=scope.user_id,
                    )
                    for scope in memory.scopes.all()
                ]
            )
        if scopes:
            MemoryScope.objects.bulk_create(scopes, ignore_conflicts=True)
        if len(scope_keys) >= 2:
            normalize_compacted_memory_owner(survivor)
        Memory.objects.filter(id__in=duplicate_ids).delete()

    if len(duplicate_groups) == batch_size:
        compact_memory_scopes.delay(batch_size=batch_size)


@app.task(trail=False)
def cleanup_orphaned_memory(
    origin_prefix: str | None = None, batch_size: int = 1000
) -> None:
    memories = Memory.objects.filter(
        scopes__isnull=True,
        legacy_project__isnull=True,
        legacy_user__isnull=True,
        legacy_shared=False,
        legacy_from_file=False,
    )
    if origin_prefix is not None:
        memories = memories.filter(origin__startswith=origin_prefix)

    memory_ids = list(memories.order_by("id").values_list("id", flat=True)[:batch_size])
    if not memory_ids:
        return

    Memory.objects.filter(id__in=memory_ids).delete()
    if len(memory_ids) == batch_size:
        cleanup_orphaned_memory.delay(
            origin_prefix=origin_prefix,
            batch_size=batch_size,
        )


def get_memory_scope_key(scope: MemoryScope) -> MemoryScopeKey:
    return (
        scope.scope,
        scope.project_id,
        scope.workspace_id,
        scope.source_project_id,
        scope.user_id,
    )


def split_automatic_scopes_from_file_memory(memory: Memory, status: int) -> Memory:
    scopes = list(memory.scopes.all())
    if not any(scope.scope in FILE_SCOPE_TYPES for scope in scopes) or not any(
        scope.scope in AUTOMATIC_SCOPE_TYPES for scope in scopes
    ):
        return memory

    automatic_scope_ids = [
        scope.id for scope in scopes if scope.scope in AUTOMATIC_SCOPE_TYPES
    ]
    if not automatic_scope_ids:
        return memory

    with transaction.atomic():
        automatic_memory = (
            Memory.objects.filter(
                source_language_id=memory.source_language_id,
                target_language_id=memory.target_language_id,
                source=memory.source,
                target=memory.target,
                origin=memory.origin,
                context=memory.context,
                status=status,
            )
            .exclude(pk=memory.pk)
            .filter_scope(Q(scope__in=AUTOMATIC_SCOPE_TYPES))
            .order_by("id")
            .first()
        )
        if automatic_memory is None:
            automatic_memory = Memory.objects.create(
                source_language_id=memory.source_language_id,
                target_language_id=memory.target_language_id,
                source=memory.source,
                target=memory.target,
                origin=memory.origin,
                context=memory.context,
                status=status,
            )
        else:
            automatic_memory.normalize_legacy_owner()
        copied_scopes = [
            MemoryScope(
                memory=automatic_memory,
                scope=scope.scope,
                project_id=scope.project_id,
                workspace_id=scope.workspace_id,
                source_project_id=scope.source_project_id,
                user_id=scope.user_id,
            )
            for scope in scopes
            if scope.scope in AUTOMATIC_SCOPE_TYPES
        ]
        MemoryScope.objects.bulk_create(copied_scopes, ignore_conflicts=True)
        MemoryScope.objects.filter(id__in=automatic_scope_ids).delete()
        memory.normalize_legacy_owner()

    automatic_memory.scope_list = None
    return automatic_memory


def collect_status_update(
    memory: Memory, status: int, to_update: list[Memory]
) -> Memory:
    if memory.status == status:
        return memory
    memory = split_automatic_scopes_from_file_memory(memory, status)
    if memory.status != status:
        memory.status = status
        to_update.append(memory)
    return memory


def normalize_compacted_memory_owner(memory: Memory) -> None:
    # Scope rows now own visibility. Keeping legacy project/user owners on a
    # multi-scope survivor would let those cascading FKs delete unrelated scopes.
    # The legacy file flag is ownership too: without project/user owners, a later
    # save would recreate the row as global file memory.
    memory.normalize_legacy_owner()


def get_memory_categories(memory: Memory) -> set[MemoryCategory]:
    categories: set[MemoryCategory] = set()
    for scope in memory.scopes.all():
        if scope.scope == MemoryScope.SCOPE_PROJECT:
            categories.add(("project", scope.project_id))
        elif scope.scope == MemoryScope.SCOPE_SHARED:
            categories.add(("shared", scope.source_project_id))
        elif scope.scope == MemoryScope.SCOPE_USER:
            categories.add(("user", scope.user_id))
        elif scope.scope == MemoryScope.SCOPE_WORKSPACE:
            categories.add(("workspace", scope.workspace_id, scope.source_project_id))
    return categories


def get_group_matching_memory(
    group_key: MemoryGroupKey,
    group_entries: list[MemoryGroupEntry],
    statuses: dict[MemoryKey, int],
) -> tuple[dict[MemoryKey, set[MemoryCategory]], list[Memory]]:
    origin, source_language_id, target_language_id = group_key
    expected_keys = sorted({key for _, key, _, _ in group_entries})
    expected_key_set = set(expected_keys)
    existing = defaultdict(set)
    to_update: list[Memory] = []
    memory_objects = Memory.objects.using("default")

    for offset in range(0, len(expected_keys), MEMORY_UPDATE_LOOKUP_CHUNK_SIZE):
        matching_pairs = Q()
        for _, _, _, source, target in expected_keys[
            offset : offset + MEMORY_UPDATE_LOOKUP_CHUNK_SIZE
        ]:
            matching_pairs |= Q(
                source__md5=MD5(Value(source)),
                target__md5=MD5(Value(target)),
            )

        matches = memory_objects.filter(
            matching_pairs,
            origin__md5=MD5(Value(origin)),
            source_language_id=source_language_id,
            target_language_id=target_language_id,
        )
        if hasattr(matches, "filter_scope"):
            matches = matches.filter_scope(Q(scope__in=AUTOMATIC_SCOPE_TYPES))
        if hasattr(matches, "prefetch_related"):
            matches = matches.prefetch_related("scopes")
        for matching in matches:
            key = (
                matching.origin,
                matching.source_language_id,
                matching.target_language_id,
                matching.source,
                matching.target,
            )
            if key not in expected_key_set:
                continue
            matching = collect_status_update(matching, statuses[key], to_update)
            existing[key].update(get_memory_categories(matching))

    return existing, to_update


def create_memory_entry(
    entry: MemoryUpdatePayload, *, status: int, category: str
) -> Memory:
    if category == "project":
        memory = Memory(
            source=entry["source"],
            context=entry["context"],
            target=entry["target"],
            origin=entry["origin"],
            source_language_id=entry["source_language_id"],
            target_language_id=entry["target_language_id"],
            status=status,
        )
        memory.pending_scopes = [
            MemoryScope(scope=MemoryScope.SCOPE_PROJECT, project_id=entry["project_id"])
        ]
        return memory
    if category == "shared":
        memory = Memory(
            source=entry["source"],
            context=entry["context"],
            target=entry["target"],
            origin=entry["origin"],
            source_language_id=entry["source_language_id"],
            target_language_id=entry["target_language_id"],
            status=status,
        )
        memory.pending_scopes = [
            MemoryScope(
                scope=MemoryScope.SCOPE_SHARED,
                source_project_id=entry["project_id"],
            )
        ]
        return memory
    if category == "workspace":
        memory = Memory(
            source=entry["source"],
            context=entry["context"],
            target=entry["target"],
            origin=entry["origin"],
            source_language_id=entry["source_language_id"],
            target_language_id=entry["target_language_id"],
            status=status,
        )
        workspace_id = entry["workspace_id"]
        if workspace_id is not None:
            memory.pending_scopes = [
                MemoryScope(
                    scope=MemoryScope.SCOPE_WORKSPACE,
                    workspace_id=workspace_id,
                    source_project_id=entry["project_id"],
                )
            ]
        return memory
    memory = Memory(
        source=entry["source"],
        context=entry["context"],
        target=entry["target"],
        origin=entry["origin"],
        source_language_id=entry["source_language_id"],
        target_language_id=entry["target_language_id"],
        status=status,
    )
    memory.pending_scopes = [
        MemoryScope(scope=MemoryScope.SCOPE_USER, user_id=entry["user_id"])
    ]
    return memory


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
        if entry["add_shared"] and ("shared", entry["project_id"]) not in categories:
            result.append(create_memory_entry(entry, status=status, category="shared"))
            categories.add(("shared", entry["project_id"]))
        workspace_id = entry["workspace_id"]
        if (
            entry["add_workspace"]
            and workspace_id is not None
            and ("workspace", workspace_id, entry["project_id"]) not in categories
        ):
            result.append(
                create_memory_entry(entry, status=status, category="workspace")
            )
            categories.add(("workspace", workspace_id, entry["project_id"]))
        user_id = entry["user_id"]
        if entry["add_user"] and ("user", user_id) not in categories:
            result.append(create_memory_entry(entry, status=status, category="user"))
            categories.add(("user", user_id))
    return result


@app.task(trail=False)
def update_memory_bulk(entries: list[MemoryUpdatePayload]) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Project

    if not entries:
        return

    projects = Project.objects.select_related("workspace").in_bulk(
        {entry["project_id"] for entry in entries}
    )
    fallback = []
    grouped_entries = defaultdict(list)
    statuses = {}
    memory_objects = Memory.objects.using("default")
    memory_scope_objects = MemoryScope.objects.db_manager("default")

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
        with transaction.atomic(using="default"):
            memory_objects.bulk_create(to_create, batch_size=MEMORY_UPDATE_BATCH_SIZE)
            memory_scope_objects.bulk_create_for_memories(to_create)

    if to_update:
        memory_objects.bulk_update(to_update, fields=["status"])
