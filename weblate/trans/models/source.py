# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Translation dependencies, independent of canonical file source relationships."""

from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from itertools import chain
from typing import TYPE_CHECKING, cast

from django.db import connections, transaction
from django.db.models import Exists, OuterRef, Q, Value
from django.db.models.functions import MD5, Lower

from weblate.trans.actions import ActionEvents
from weblate.trans.source_snapshot import MissingSourceCache, SourceSnapshot
from weblate.utils.state import (
    FUZZY_STATES,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable
    from typing import Any

    from weblate.auth.models import User
    from weblate.memory.tasks import MemoryUpdatePayload
    from weblate.trans.models.change import Change
    from weblate.trans.models.component import Component
    from weblate.trans.models.translation import Translation
    from weblate.trans.models.unit import Unit, UnitQuerySet


@dataclass
class DependencyWork:
    roots: set[int] = field(default_factory=set)
    children: set[int] = field(default_factory=set)
    languages: set[int] = field(default_factory=set)
    full: bool = False
    force: bool = False
    batch_checks: bool = False
    author: User | None = None

    def merge(self, other: DependencyWork) -> None:
        self.roots.update(other.roots)
        self.children.update(other.children)
        self.languages.update(other.languages)
        self.full |= other.full
        self.force |= other.force
        self.batch_checks |= other.batch_checks
        if other.author is not None:
            self.author = other.author


_operations: ContextVar[dict[tuple[str, int], DependencyWork] | None] = ContextVar(
    "source_operations", default=None
)


@dataclass
class SourceWorkflowGate:
    workflows: dict[int, int]
    exclusive: bool


_gates: ContextVar[dict[tuple[str, int], SourceWorkflowGate] | None] = ContextVar(
    "source_workflow_gates", default=None
)


@contextmanager
def source_project_gate(
    project_ids: Iterable[int], *, using: str = "default", exclusive: bool = False
) -> Generator[None, None, None]:
    """Lock before unit writes; workflow changes require an exclusive outer gate."""
    from weblate.checks.tasks import coalesce_component_check_batches  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models.project import Project  # ruff: ignore[import-outside-top-level]

    active = _gates.get() or {}
    project_ids = sorted(set(project_ids))
    missing = [
        project_id for project_id in project_ids if (using, project_id) not in active
    ]
    if exclusive and any(
        not active[using, project_id].exclusive
        for project_id in project_ids
        if (using, project_id) in active
    ):
        msg = "Source workflow changes require an exclusive outer operation"
        raise RuntimeError(msg)
    if not missing:
        if not exclusive:
            yield
            return
        previous = {key: dict(gate.workflows) for key, gate in active.items()}
        try:
            with (
                transaction.atomic(using=using),
                coalesce_component_check_batches(using=using),
            ):
                yield
        except BaseException:
            for key, workflows in previous.items():
                active[key].workflows = workflows
            Project.invalidate_translation_parent_cache()
            raise
        return
    gates = dict(active)
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            for project_id in missing:
                cursor.execute(
                    "SELECT weblate_source_workflow_gate(%s, %s)",
                    [project_id, exclusive],
                )
                data = cursor.fetchone()[0]
                if isinstance(data, str):
                    data = json.loads(data)
                gates[using, project_id] = SourceWorkflowGate(
                    {int(language): source for language, source in data.items()},
                    exclusive,
                )
        token = _gates.set(gates)
        try:
            with (
                coalesce_component_check_batches(using=using)
                if exclusive
                else nullcontext()
            ):
                yield
        except BaseException:
            Project.invalidate_translation_parent_cache()
            raise
        finally:
            _gates.reset(token)


def refresh_source_workflows(project_id: int, *, using: str = "default") -> set[int]:
    """Refresh configuration and return changed languages and their dependants."""
    from weblate.trans.models.workflow import WorkflowSetting  # ruff: ignore[import-outside-top-level]

    gate = (_gates.get() or {}).get((using, project_id))
    if gate is not None:
        previous = gate.workflows
        gate.workflows = dict(
            WorkflowSetting.objects.using(using)
            .filter(project_id=project_id, source_language__isnull=False)
            .values_list("language_id", "source_language_id")
        )
        affected = {
            language
            for language in previous.keys() | gate.workflows.keys()
            if previous.get(language) != gate.workflows.get(language)
        }
        pending = set(affected)
        while pending:
            children = {
                language
                for workflows in (previous, gate.workflows)
                for language, source in workflows.items()
                if source in pending
            } - affected
            affected.update(children)
            pending = children
        return affected
    return set()


def current_source_workflows(
    project_id: int, *, using: str = "default"
) -> dict[int, int] | None:
    gate = (_gates.get() or {}).get((using, project_id))
    return gate.workflows if gate is not None else None


def source_workflows(project_id: int, *, using: str = "default") -> dict[int, int]:
    """Return the workflow view protected by the current transaction's gate."""
    return (_gates.get() or {})[using, project_id].workflows


@contextmanager
def source_operation(component: Component) -> Generator[None, None, None]:
    """Flush dependencies before commit; nested rollbacks discard their own work."""
    using = component._state.db or "default"  # ruff: ignore[private-member-access]
    key = (using, component.pk)
    active = _operations.get() or {}
    work = DependencyWork()
    nested_gate = (using, component.project_id) in (_gates.get() or {})
    with source_project_gate([component.project_id], using=using):
        component.project.cache_translation_parent_language_ids(
            set(source_workflows(component.project_id, using=using).values())
        )
        token = _operations.set({**active, key: work})
        try:
            with transaction.atomic(using=using) if nested_gate else nullcontext():
                yield
                if key not in active and (
                    work.full or work.languages or work.roots or work.children
                ):
                    _reconcile(component, work)
            if key in active:
                active[key].merge(work)
        finally:
            _operations.reset(token)


def source_operation_method[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """Batch dependency work around Unit, Translation, and Component operations."""

    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        instance = cast("Any", args[0])
        if kwargs.get("only_save"):
            return method(*args, **kwargs)
        if hasattr(instance, "translation"):
            component = instance.translation.component
        else:
            component = getattr(instance, "component", instance)
        with source_operation(component):
            return method(*args, **kwargs)

    return wrapped


def request_reconciliation(component: Component, work: DependencyWork) -> None:
    using = component._state.db or "default"  # ruff: ignore[private-member-access]
    key = (using, component.pk)
    active = _operations.get() or {}
    if key in active:
        active[key].merge(work)
    else:
        with source_operation(component):
            (_operations.get() or {})[key].merge(work)


@dataclass
class PreviousSourcePeers:
    unit: Unit
    source: str
    language_id: int
    excluded: set[int]


@dataclass
class ReconciliationEffects:
    batch_checks: bool = False
    units: dict[int, Unit] = field(default_factory=dict)
    peer_groups: dict[tuple[int, str, int, int, str, str], PreviousSourcePeers] = field(
        default_factory=dict
    )
    memory: list[MemoryUpdatePayload] = field(default_factory=list)

    def propagate_checks(self, unit: Unit) -> None:
        from weblate.checks.base import BatchCheckMixin  # ruff: ignore[import-outside-top-level]
        from weblate.checks.models import CHECKS  # ruff: ignore[import-outside-top-level]
        from weblate.checks.tasks import schedule_propagated_checks  # ruff: ignore[import-outside-top-level]

        checks = {
            name
            for name, check in CHECKS.items()
            if check.propagates
            and not (self.batch_checks and isinstance(check, BatchCheckMixin))
        }
        if checks:
            schedule_propagated_checks(unit, checks)

    def add_peers(self, unit: Unit, source: str, language_id: int) -> None:
        key = (
            unit.translation.component_id,
            source,
            language_id,
            unit.translation.plural_id,
            unit.context,
            unit.target,
        )
        if key in self.peer_groups:
            # Each original query excludes only its initiating unit. Their union
            # excludes it only if every query does so.
            self.peer_groups[key].excluded.intersection_update({unit.pk})
        else:
            self.peer_groups[key] = PreviousSourcePeers(
                unit, source, language_id, {unit.pk}
            )

    def flush(self, *, using: str) -> None:
        from weblate.memory.tasks import schedule_memory_updates  # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.unit import Unit  # ruff: ignore[import-outside-top-level]

        if self.batch_checks:
            self.flush_batched_checks(using=using)
            batched_translations = {
                unit.translation_id: unit.translation for unit in self.units.values()
            }
            for translation in batched_translations.values():
                translation.invalidate_cache()
            schedule_memory_updates(self.memory)
            return
        peers: set[int] = set()
        for group in self.peer_groups.values():
            peers.update(
                previous_source_peers(group.unit, group.source, group.language_id)
                .exclude(pk__in=group.excluded)
                .values_list("pk", flat=True)
            )
        translations: dict[int, Translation] = {}
        for unit in self.units.values():
            translations.setdefault(unit.translation_id, unit.translation)
        peer_units = (
            Unit.objects.using(using)
            .filter(pk__in=peers - self.units.keys())
            .prefetch()
            .prefetch_bulk()
        )
        for unit in chain(self.units.values(), peer_units):
            unit.translation = translations.setdefault(
                unit.translation_id, unit.translation
            )
            unit.invalidate_checks_cache()
            unit.run_checks(skip_propagate=unit.pk not in self.units)
        for translation in translations.values():
            translation.invalidate_cache()
        schedule_memory_updates(self.memory)

    def flush_batched_checks(self, *, using: str) -> None:
        from weblate.checks.base import BatchCheckMixin  # ruff: ignore[import-outside-top-level]
        from weblate.checks.locks import check_project_read_lock  # ruff: ignore[import-outside-top-level]
        from weblate.checks.models import CHECKS  # ruff: ignore[import-outside-top-level]
        from weblate.checks.tasks import schedule_component_check_batch  # ruff: ignore[import-outside-top-level]

        if not self.units:
            return
        component = next(iter(self.units.values())).translation.component
        previous = (
            component.batch_checks,
            component.batched_checks,
            component.updated_sources,
        )
        component.start_batched_checks()
        component.updated_sources = set()
        try:
            # Hold the check boundary once while local checks retain the existing
            # results of batch-capable peer checks. Workers evaluate those batches.
            with check_project_read_lock(component) as changed:
                for unit in self.units.values():
                    unit.translation.component = component
                    was_batch_update = unit.is_batch_update
                    try:
                        unit.is_batch_update = True
                        if changed:
                            unit.clear_checks_cache()
                        unit.invalidate_checks_cache()
                        unit._run_checks_unlocked()  # ruff: ignore[private-member-access]
                    finally:
                        unit.is_batch_update = was_batch_update
            # Removed/blocked units can no longer register their old peer group.
            # Rebuilding the boundary also removes warnings on those peers.
            if component.allow_translation_propagation:
                component.batched_checks.update(
                    name for name in ("inconsistent", "reused") if name in CHECKS
                )
            component.batched_checks.update(
                name
                for name, check in CHECKS.source.items()
                if isinstance(check, BatchCheckMixin)
            )
            if previous[0]:
                previous[1].update(component.batched_checks)
                previous[2].update(component.updated_sources)
            schedule_component_check_batch(
                component,
                component.updated_sources,
                component.batched_checks,
                using=using,
            )
        finally:
            (
                component.batch_checks,
                component.batched_checks,
                component.updated_sources,
            ) = previous


def _update_previous_source(
    unit: Unit, previous: SourceSnapshot, current: SourceSnapshot
) -> None:
    """Retain the first pending source without accepting an existing fuzzy target."""
    metadata = unit.details["translation_parent"]
    state = unit.original_state if unit.state == STATE_READONLY else unit.state
    was_fuzzy = metadata.get("previous_state", STATE_TRANSLATED) in FUZZY_STATES
    if (
        "previous" in metadata
        and SourceSnapshot.from_dict(metadata["previous"]).identity == current.identity
        and metadata.get("canonical_source") == unit.source
        and (was_fuzzy or (state == STATE_NEEDS_REWRITING and not unit.previous_source))
    ):
        if not was_fuzzy:
            unit.original_state = STATE_TRANSLATED
            if unit.state != STATE_READONLY:
                unit.state = STATE_TRANSLATED
        metadata.pop("previous", None)
        metadata.pop("canonical_source", None)
        metadata.pop("previous_state", None)
    elif unit.target and (
        STATE_TRANSLATED <= state < STATE_READONLY
        or (state in FUZZY_STATES and "previous" not in metadata)
    ):
        metadata.update(
            previous=previous.as_dict(),
            canonical_source=unit.source,
            previous_state=state,
        )
        if state >= STATE_TRANSLATED:
            unit.original_state = STATE_NEEDS_REWRITING
            if unit.state != STATE_READONLY:
                unit.state = STATE_NEEDS_REWRITING


def update_parent(
    unit: Unit,
    parent: Unit | None,
    author: User | None = None,
    *,
    effects: ReconciliationEffects,
    force: bool = False,
    configured: bool | None = None,
    missing_sources: MissingSourceCache | None = None,
    pending_author_id: int | None = None,
) -> Change | None:
    """Apply a dependency change without modifying canonical source data."""
    from weblate.trans.models.pending import PendingUnitChange  # ruff: ignore[import-outside-top-level]

    old_state = unit.state
    old_parent = unit.translation_parent_id
    metadata = unit.details.setdefault("translation_parent", {})
    old_missing = "missing" in metadata
    if configured is None:
        configured = unit.translation.has_custom_source
    previous = (
        SourceSnapshot.from_dict(metadata["applied"])
        if "applied" in metadata
        else SourceSnapshot.from_unit(unit, canonical=True)
    )
    previous_source = previous.text
    previous_language_id = previous.language_id
    unit.translation_parent = parent
    unit.update_missing_source(missing_sources)
    current = unit.source_snapshot
    changed = previous.identity != current.identity
    initializing = configured and "applied" not in metadata
    old_blocked = metadata.get("blocked", False)
    if changed:
        _update_previous_source(unit, previous, current)

    words_changed = unit.num_words != unit.effective_source_num_words
    blocked = unit.translation_parent_blocked
    metadata["blocked"] = blocked
    if blocked and unit.state != STATE_READONLY:
        unit.original_state = unit.state
        unit.state = STATE_READONLY
    elif (
        old_blocked
        and not blocked
        and unit.state == STATE_READONLY
        and "read-only" not in unit.all_flags
        and not (
            unit.translation.component.intermediate
            and unit.source_unit.state < STATE_TRANSLATED
        )
    ):
        unit.state = unit.original_state

    keep_snapshot = configured or "previous" in metadata or blocked
    discard_snapshot = not keep_snapshot and "applied" in metadata
    if not keep_snapshot:
        unit.details.pop("translation_parent", None)
    if not (
        force
        or discard_snapshot
        or initializing
        or changed
        or words_changed
        or old_parent != unit.translation_parent_id
        or old_blocked != blocked
        or old_missing != ("missing" in metadata)
    ):
        return None
    if keep_snapshot:
        metadata["applied"] = current.as_dict()
    unit.save(
        only_save=True,
        same_content=False,
        update_fields=["translation_parent", "details", "state", "original_state"],
    )
    effects.units[unit.pk] = unit
    if changed:
        effects.propagate_checks(unit)
    if not effects.batch_checks and (
        changed or old_parent != unit.translation_parent_id or old_blocked != blocked
    ):
        effects.add_peers(unit, previous_source, previous_language_id)
    actor = (
        author
        if author is not None
        else unit.translation.component.get_update_user(None)
    )
    if unit.state != old_state or changed:
        PendingUnitChange.store_unit_change(
            unit=unit, author=author, author_id=pending_author_id, user=actor
        )
    change = None
    if changed:
        change = unit.generate_change(
            actor,
            author,
            ActionEvents.SOURCE_CHANGE,
            check_new=False,
            save=False,
            old=previous_source,
            target=current.text,
            change_details={
                "source_snapshot": current.as_dict(),
                "previous_source_snapshot": previous.as_dict(),
                "source": current.text,
            },
        )
    unit.update_translation_memory(
        author, needs_user_check=False, memory_updates=effects.memory
    )
    return change


def previous_source_peers(
    unit: Unit, previous_source: str, previous_language_id: int
) -> UnitQuerySet:
    """Find cross-unit failures in groups the unit no longer belongs to."""
    from weblate.trans.models.unit import Unit  # ruff: ignore[import-outside-top-level]
    from weblate.trans.propagation import propagation_filter  # ruff: ignore[import-outside-top-level]

    matches = Q(check_source=previous_source, context=unit.context)
    if unit.target:
        matches |= Q(
            target=unit.target, target__lower__md5=MD5(Lower(Value(unit.target)))
        )
    using = unit._state.db or "default"  # ruff: ignore[private-member-access]
    return (
        Unit.objects.using(using)
        .with_effective_source()
        .filter(
            matches,
            propagation_filter(
                unit.translation.component.project,
                "translation__component__",
                unit.translation.component.name,
            ),
            check__name__in=("inconsistent", "reused"),
            check_source_language=previous_language_id,
            translation__component__allow_translation_propagation=True,
            translation__plural_id=unit.translation.plural_id,
        )
        .distinct()
    )


def propagate_parent_change(
    translation: Translation,
    unit_id: int,
    author: User | None = None,
    *,
    created: bool = False,
) -> None:
    """Queue parent writes, including links to newly available source units."""
    component = translation.component
    using = component._state.db or "default"  # ruff: ignore[private-member-access]
    workflows = current_source_workflows(component.project_id, using=using)
    if workflows is None:
        with source_operation(component):
            propagate_parent_change(translation, unit_id, author, created=created)
    elif translation.language_id in workflows.values():
        request_reconciliation(
            component, DependencyWork(roots={unit_id}, full=created, author=author)
        )


def _reconcile(component: Component, work: DependencyWork) -> None:
    from weblate.trans.models.change import Change  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models.unit import Unit  # ruff: ignore[import-outside-top-level]

    using = component._state.db or "default"  # ruff: ignore[private-member-access]
    component_units = Unit.objects.using(using).filter(translation__component=component)
    queryset = component_units
    settings = None
    if work.full or work.languages:
        settings = source_workflows(component.project_id, using=using)
        component.project.cache_translation_parent_language_ids(set(settings.values()))
        if (
            not settings
            and not queryset.filter(
                Q(translation_parent__isnull=False)
                | Q(details__has_key="translation_parent")
            ).exists()
        ):
            return
    if not work.full:
        affected = set(work.children)
        pending = work.roots | work.children
        visited = set()
        while pending:
            visited.update(pending)
            children = set(
                queryset.filter(translation_parent_id__in=pending).values_list(
                    "pk", flat=True
                )
            )
            affected.update(children)
            pending = children - visited
        queryset = queryset.filter(
            Q(pk__in=affected) | Q(translation__language_id__in=work.languages)
        )
    anonymous_id = None
    if work.author is None:
        from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]

        queryset = queryset.with_last_content_author()
        anonymous_id = get_anonymous().pk
    units = list(
        queryset.select_for_update().prefetch().prefetch_source().prefetch_all_checks()
    )
    by_id = {unit.pk: unit for unit in units}
    by_identity = {(unit.translation.language_id, unit.id_hash): unit for unit in units}
    if settings is not None and not work.full:
        parent_languages = {
            settings[unit.translation.language_id]
            for unit in units
            if unit.translation.language_id in settings
        } - {component.source_language_id}
        supporting_parents = (
            component_units.filter(
                translation__language_id__in=parent_languages,
                id_hash__in=queryset.order_by().values("id_hash"),
            )
            .exclude(pk__in=queryset.order_by().values("pk"))
            .prefetch()
            .prefetch_source()
        )
        by_identity.update(
            ((unit.translation.language_id, unit.id_hash), unit)
            for unit in supporting_parents
        )
    parents = {}
    for unit in units:
        parent = unit.translation_parent
        if settings is not None:
            parent = (
                None
                if unit.is_source
                or settings.get(unit.translation.language_id)
                == component.source_language_id
                else by_identity.get(
                    (settings.get(unit.translation.language_id), unit.id_hash)
                )
            )
            if parent is not None and parent.is_source:
                parent = None
        elif parent is not None:
            parent = by_id.get(parent.pk, parent)
        parents[unit.pk] = parent

    def depth(unit: Unit) -> int:
        visited = {unit.pk}
        parent = parents[unit.pk]
        while parent is not None and parent.pk not in visited:
            visited.add(parent.pk)
            parent = parents.get(parent.pk)
        return len(visited)

    missing_sources: MissingSourceCache = {}
    effects = ReconciliationEffects(batch_checks=work.batch_checks)
    changes = []
    for unit in sorted(units, key=depth):
        change = update_parent(
            unit,
            parents[unit.pk],
            work.author,
            effects=effects,
            force=work.force,
            missing_sources=missing_sources,
            pending_author_id=(
                unit.last_content_author_id or anonymous_id
                if work.author is None
                else None
            ),
            configured=(
                not unit.is_source
                and settings.get(unit.translation.language_id)
                not in {None, component.source_language_id}
                if settings is not None
                else None
            ),
        )
        if change is not None:
            changes.append(change)
    effects.flush(using=using)
    if changes:
        Change.objects.using(using).bulk_create(changes, batch_size=500)


def reconcile_component_parents(
    component: Component,
    *,
    force: bool = False,
    language_ids: set[int] | None = None,
    batch_checks: bool = False,
) -> None:
    """Rebuild relationships, optionally restricted to affected languages."""
    if language_ids is not None and not language_ids:
        return
    request_reconciliation(
        component,
        DependencyWork(
            full=language_ids is None,
            languages=language_ids or set(),
            force=force,
            batch_checks=batch_checks,
        ),
    )


def reconcile_project_parents(
    project_id: int | None,
    *,
    force: bool = False,
    language_ids: set[int] | None = None,
    using: str = "default",
    batch_checks: bool = False,
) -> None:
    if project_id is None or language_ids == set():
        return
    from weblate.trans.models.component import Component  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models.translation import Translation  # ruff: ignore[import-outside-top-level]

    components = Component.objects.using(using).filter(project_id=project_id)
    if language_ids is not None:
        components = components.filter(
            Exists(
                Translation.objects.using(using).filter(
                    component_id=OuterRef("pk"), language_id__in=language_ids
                )
            )
        )
    for component in components.order_by("pk"):
        reconcile_component_parents(
            component, force=force, language_ids=language_ids, batch_checks=batch_checks
        )
