# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Translation dependencies, independent of canonical file source relationships."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, cast

from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import MD5, Lower

from weblate.trans.actions import ActionEvents
from weblate.trans.source_snapshot import SourceSnapshot
from weblate.utils.state import STATE_NEEDS_REWRITING, STATE_READONLY, STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import Any

    from weblate.auth.models import User
    from weblate.trans.models.component import Component
    from weblate.trans.models.translation import Translation
    from weblate.trans.models.unit import Unit


@dataclass
class DependencyWork:
    roots: set[int] = field(default_factory=set)
    children: set[int] = field(default_factory=set)
    full: bool = False
    force: bool = False
    author: User | None = None

    def merge(self, other: DependencyWork) -> None:
        self.roots.update(other.roots)
        self.children.update(other.children)
        self.full |= other.full
        self.force |= other.force
        if other.author is not None:
            self.author = other.author


_operations: ContextVar[dict[tuple[str, int], DependencyWork] | None] = ContextVar(
    "source_operations", default=None
)


@contextmanager
def source_operation(component: Component, *, required: bool = False) -> Iterator[None]:
    """Flush dependencies before commit; nested rollbacks discard their own work."""
    using = component._state.db or "default"  # ruff: ignore[private-member-access]
    key = (using, component.pk)
    active = _operations.get() or {}
    if (
        not required
        and key not in active
        and not component.project.translation_parent_language_ids
    ):
        yield
        return
    work = DependencyWork()
    token = _operations.set({**active, key: work})
    try:
        with transaction.atomic(using=using):
            yield
            if key not in active and (work.full or work.roots or work.children):
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
        with source_operation(component, required=True):
            (_operations.get() or {})[key].merge(work)


def update_parent(
    unit: Unit,
    parent: Unit | None,
    author: User | None = None,
    *,
    force: bool = False,
    configured: bool | None = None,
) -> None:
    """Apply a dependency change without modifying canonical source data."""
    from weblate.trans.models.pending import PendingUnitChange  # ruff: ignore[import-outside-top-level]

    old_state = unit.state
    old_parent = unit.translation_parent_id
    metadata = unit.details.setdefault("translation_parent", {})
    if configured is None:
        configured = parent is not None or "applied" in metadata
    previous = (
        SourceSnapshot.from_dict(metadata["applied"])
        if "applied" in metadata
        else SourceSnapshot.from_unit(unit, canonical=True)
    )
    previous_source = previous.text
    previous_language_id = previous.language_id
    unit.translation_parent = parent
    current = unit.source_snapshot
    changed = previous.identity != current.identity
    initializing = configured and "applied" not in metadata
    old_blocked = metadata.get("blocked", False)
    state = unit.original_state if unit.state == STATE_READONLY else unit.state
    if changed:
        if (
            "previous" in metadata
            and SourceSnapshot.from_dict(metadata["previous"]).identity
            == current.identity
            and metadata.get("canonical_source") == unit.source
            and state == STATE_NEEDS_REWRITING
            and not unit.previous_source
        ):
            unit.original_state = STATE_TRANSLATED
            if unit.state != STATE_READONLY:
                unit.state = STATE_TRANSLATED
            metadata.clear()
        elif STATE_TRANSLATED <= state < STATE_READONLY and unit.target:
            metadata.update(
                previous=previous.as_dict(),
                canonical_source=unit.source,
            )
            unit.original_state = STATE_NEEDS_REWRITING
            if unit.state != STATE_READONLY:
                unit.state = STATE_NEEDS_REWRITING

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
    ):
        return
    if keep_snapshot:
        metadata["applied"] = current.as_dict()
    unit.save(
        only_save=True,
        same_content=False,
        update_fields=["translation_parent", "details", "state", "original_state"],
    )
    unit.invalidate_checks_cache()
    unit.run_checks()
    if changed or old_parent != unit.translation_parent_id or old_blocked != blocked:
        recheck_previous_source_peers(unit, previous_source, previous_language_id)
    if unit.state != old_state or changed:
        PendingUnitChange.store_unit_change(unit=unit, author=author)
    if changed:
        unit.generate_change(
            author,
            author,
            ActionEvents.SOURCE_CHANGE,
            check_new=False,
            old=previous_source,
            target=current.text,
            change_details={
                "source_snapshot": current.as_dict(),
                "previous_source_snapshot": previous.as_dict(),
                "source": current.text,
            },
        )
    unit.update_translation_memory(author, needs_user_check=False)
    unit.translation.invalidate_cache()


def recheck_previous_source_peers(
    unit: Unit, previous_source: str, previous_language_id: int
) -> None:
    """Clear cross-unit failures in groups the unit no longer belongs to."""
    from weblate.trans.models.unit import Unit  # ruff: ignore[import-outside-top-level]

    matches = Q(check_source=previous_source, context=unit.context)
    if unit.target:
        matches |= Q(
            target=unit.target, target__lower__md5=MD5(Lower(Value(unit.target)))
        )
    peers = (
        Unit.objects.with_effective_source()
        .filter(
            matches,
            check__name__in=("inconsistent", "reused"),
            check_source_language=previous_language_id,
            translation__component__project_id=unit.translation.component.project_id,
            translation__component__allow_translation_propagation=True,
            translation__plural_id=unit.translation.plural_id,
        )
        .exclude(pk=unit.pk)
        .distinct()
        .prefetch()
        .prefetch_bulk()
    )
    for peer in peers:
        peer.run_checks(skip_propagate=True)
        peer.translation.invalidate_cache()


def propagate_parent_change(
    translation: Translation, unit_id: int, author: User | None = None
) -> None:
    """Queue eligible parent edits; reconciliation loads the current units."""
    component = translation.component
    if translation.language_id in component.project.translation_parent_language_ids:
        request_reconciliation(
            component, DependencyWork(roots={unit_id}, author=author)
        )


def _reconcile(component: Component, work: DependencyWork) -> None:
    from weblate.trans.models.unit import Unit  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models.workflow import WorkflowSetting  # ruff: ignore[import-outside-top-level]

    using = component._state.db or "default"  # ruff: ignore[private-member-access]
    with component.lock if work.full else nullcontext():
        queryset = Unit.objects.using(using).filter(translation__component=component)
        settings = None
        if work.full:
            settings = dict(
                WorkflowSetting.objects.using(using)
                .filter(project_id=component.project_id)
                .exclude(source_language=None)
                .values_list("language_id", "source_language_id")
            )
            component.project.cache_translation_parent_language_ids(
                set(settings.values())
            )
            if (
                not settings
                and not queryset.filter(
                    Q(translation_parent__isnull=False)
                    | Q(details__has_key="translation_parent")
                ).exists()
            ):
                return
        else:
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
            queryset = queryset.filter(pk__in=affected)
        units = list(queryset.select_for_update().prefetch().prefetch_source())
        by_id = {unit.pk: unit for unit in units}
        by_identity = {
            (unit.translation.language_id, unit.id_hash): unit for unit in units
        }
        parents = {}
        for unit in units:
            parent = unit.translation_parent
            if settings is not None:
                parent = (
                    None
                    if unit.is_source
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

        for unit in sorted(units, key=depth):
            update_parent(
                unit,
                parents[unit.pk],
                work.author,
                force=work.force,
                configured=(
                    not unit.is_source and unit.translation.language_id in settings
                    if settings is not None
                    else None
                ),
            )


def reconcile_component_parents(component: Component, *, force: bool = False) -> None:
    """Register a complete relationship rebuild, including removed workflows."""
    request_reconciliation(component, DependencyWork(full=True, force=force))


def reconcile_project_parents(project_id: int | None, *, force: bool = False) -> None:
    if project_id is None:
        return
    from weblate.trans.models.component import Component  # ruff: ignore[import-outside-top-level]

    for component in Component.objects.filter(project_id=project_id).order_by("pk"):
        reconcile_component_parents(component, force=force)
