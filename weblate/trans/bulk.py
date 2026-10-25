# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from itertools import batched
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext

from weblate.checks.flags import Flags, FlagsValidator
from weblate.trans.actions import ActionEvents
from weblate.trans.autofixes import fix_target
from weblate.trans.models import Change, Component, Unit
from weblate.trans.models.pending import PendingUnitChange
from weblate.trans.models.source import propagate_parent_change, source_operation
from weblate.utils.bulk_regex import regex_session, replace_regex, validate_regex
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_TRANSLATED,
    StringState,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from django.db.models import QuerySet

    from weblate.addons.ai import EvaluatedUnitSnapshot
    from weblate.auth.models import User
    from weblate.trans.models import Label, Project
    from weblate.trans.models.unit import UnitQuerySet

BULK_EDIT_PREVIEW_LIMIT = 250

EDITABLE_STATES = {
    STATE_FUZZY,
    STATE_NEEDS_REWRITING,
    STATE_NEEDS_CHECKING,
    STATE_TRANSLATED,
    STATE_APPROVED,
}


def exclude_stale_evaluations(
    units: UnitQuerySet,
    snapshots: dict[int, EvaluatedUnitSnapshot],
) -> UnitQuerySet:
    """
    Lock and retain targets whose evaluated target and source are unchanged.

    This deliberately guarantees only that the target and source content used by
    AI quality evaluation still match immediately before approval. It does not
    hold locks during the provider request or version every mutable prompt input.
    """
    from weblate.addons.ai import evaluation_snapshot  # ruff: ignore[import-outside-top-level]

    selected_ids = set(
        units.exclude(pk=F("source_unit_id")).values_list("pk", flat=True)
    )
    relevant = {pk: snapshots[pk] for pk in selected_ids & snapshots.keys()}
    locked: dict[int, Unit] = {}
    lock_ids = {
        item_id
        for pk, snapshot in relevant.items()
        for item_id in (pk, snapshot.source_unit_id)
    }
    # Bound each lock query for large result scopes while retaining all acquired
    # row locks until the surrounding bulk-operation transaction commits.
    for chunk in batched(sorted(lock_ids), 1000):
        locked.update(
            (unit.pk, unit)
            for unit in Unit.objects.filter(pk__in=chunk)
            .order_by("pk")
            .select_related("translation")
            .select_for_update()
        )
    valid_ids = {
        pk
        for pk, snapshot in relevant.items()
        if pk in locked
        and snapshot.source_unit_id in locked
        and locked[pk].source_unit_id == snapshot.source_unit_id
        and evaluation_snapshot(locked[pk]).fingerprint == snapshot.unit.fingerprint
        and evaluation_snapshot(locked[snapshot.source_unit_id]).fingerprint
        == snapshot.source_unit.fingerprint
    }
    return units.filter(pk__in=valid_ids)


@dataclass
class BulkReplacement:
    search: str = ""
    replacement: str = ""
    search_type: str = "text"
    prepared: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        if self.search_type not in {"text", "regex"}:
            raise ValidationError(gettext("Invalid search type."))
        if not self.search and self.replacement:
            raise ValidationError(gettext("Enter a search string to replace."))
        if self.search and self.search_type == "regex":
            validate_regex(self.search, self.replacement)

    def prepare(self, units: list[Unit]) -> None:
        self.prepared.clear()
        if not self.search or self.search_type != "regex":
            return
        values = [value for unit in units for value in unit.get_target_plurals()]
        results = replace_regex(self.search, self.replacement, values)
        self.prepared.update(zip(values, results, strict=True))

    def replace(self, value: str) -> str:
        if not self.search:
            return value
        if self.search_type == "text":
            return value.replace(self.search, self.replacement)
        if value in self.prepared:
            return self.prepared[value]
        return replace_regex(self.search, self.replacement, [value])[0]


@dataclass
class BulkUnitEdit:
    unit: Unit
    target: list[str] | None = None
    state: int | None = None
    source_flags: str | None = None
    translation_flags: str | None = None
    add_labels: set[int] = field(default_factory=set)
    remove_labels: set[int] = field(default_factory=set)

    @property
    def state_label(self) -> str:
        return str(StringState(self.state).label) if self.state is not None else ""

    @property
    def changed(self) -> bool:
        return (
            self.state is not None
            or self.source_flags is not None
            or self.translation_flags is not None
            or bool(self.add_labels or self.remove_labels)
        )


def changed_flags(unit: Unit, add: str | Flags, remove: str | Flags) -> str | None:
    if not add and not remove:
        return None
    flags = unit.get_unit_flags()
    flags.merge(add)
    flags.remove(remove)
    value = flags.format()
    return value if value != unit.extra_flags else None


def can_bulk_edit_target(
    unit: Unit, user: User | None, target_state: int, *, enforce_permissions: bool
) -> bool:
    return bool(
        not unit.readonly
        and (
            not enforce_permissions
            or (
                user is not None
                and user.has_perm("unit.edit", unit)
                and user.has_perm(
                    "unit.bulk_edit",
                    unit.translation.component if unit.is_source else unit,
                )
                and (
                    target_state != STATE_APPROVED or user.has_perm("unit.review", unit)
                )
            )
        )
    )


def plan_bulk_units(
    units: Iterable[Unit],
    planner: Callable[[Unit], BulkUnitEdit],
    replacement: BulkReplacement,
    user: User | None,
    target_state: int,
    *,
    enforce_permissions: bool,
) -> Iterator[BulkUnitEdit]:
    """Prepare regex results in bounded batches, retaining per-unit eligibility."""
    for chunk in batched(units, BULK_EDIT_PREVIEW_LIMIT):
        if (
            replacement.search
            and replacement.search_type == "regex"
            and target_state != STATE_EMPTY
        ):
            replacement.prepare(
                [
                    unit
                    for unit in chunk
                    if can_bulk_edit_target(
                        unit,
                        user,
                        target_state,
                        enforce_permissions=enforce_permissions,
                    )
                ]
            )
        try:
            for unit in chunk:
                yield planner(unit)
        finally:
            replacement.prepared.clear()


def plan_bulk_unit(
    unit: Unit,
    user: User | None,
    *,
    target_state: int,
    replacement: BulkReplacement,
    add_flags: str | Flags,
    remove_flags: str | Flags,
    add_translation_flags: str | Flags,
    remove_translation_flags: str | Flags,
    add_labels: set[int],
    remove_labels: set[int],
    enforce_permissions: bool,
) -> BulkUnitEdit:
    """Calculate a candidate's changes without storing anything."""
    edit = BulkUnitEdit(unit)
    component = unit.translation.component
    trusted = not enforce_permissions
    if can_bulk_edit_target(
        unit, user, target_state, enforce_permissions=enforce_permissions
    ):
        old_target = unit.get_target_plurals()
        target = old_target
        state = unit.state
        if target_state == STATE_EMPTY:
            if not unit.is_source:
                target = [""] * len(old_target)
                state = STATE_EMPTY
        else:
            target = [replacement.replace(value) for value in old_target]
            if target_state != -1 and (unit.state in EDITABLE_STATES or any(target)):
                state = target_state
        if target != old_target:
            if not unit.translation.is_template:
                target, _fixups = fix_target(target, unit)
            if not any(target):
                if unit.is_source:
                    target = old_target
                else:
                    state = STATE_EMPTY
            elif state == STATE_EMPTY:
                state = STATE_TRANSLATED
        if target != old_target or state != unit.state:
            edit.target = target if target != old_target else None
            edit.state = state

    if trusted or (
        user is not None
        and user.has_perm("source.edit", component)
        and user.has_perm("unit.bulk_edit", component)
    ):
        source = unit.source_unit
        edit.source_flags = changed_flags(source, add_flags, remove_flags)
        if add_labels or remove_labels:
            current = {label.pk for label in source.labels.all()}
            # Removing wins, matching the existing add-then-remove behavior.
            edit.add_labels = add_labels - current - remove_labels
            edit.remove_labels = current & remove_labels
    if not unit.is_source and (
        trusted
        or (
            user is not None
            and user.has_perm("meta:unit.flag", unit.translation)
            and user.has_perm("unit.bulk_edit", unit)
        )
    ):
        edit.translation_flags = changed_flags(
            unit, add_translation_flags, remove_translation_flags
        )
    return edit


def lock_bulk_sources(units: UnitQuerySet) -> None:
    """Serialize source metadata changes before locking any sibling targets."""
    list(
        Unit.objects.filter(pk__in=units.values_list("source_unit_id", flat=True))
        .order_by("pk")
        .select_for_update()
        .values_list("pk", flat=True)
    )


def apply_bulk_translation_flags(
    user: User,
    component: Component,
    edits: list[BulkUnitEdit],
    changed_ids: set[int],
    changed_sources: set[int],
) -> bool:
    """Read current source flags and unit state after all source metadata edits."""
    flags = {
        edit.unit.pk: edit.translation_flags
        for edit in edits
        if edit.translation_flags is not None
    }
    updated = False
    for unit in (
        Unit.objects.filter(pk__in=flags)
        .order_by("pk")
        .select_for_update()
        .prefetch()
        .prefetch_bulk()
        .iterator(chunk_size=BULK_EDIT_PREVIEW_LIMIT)
    ):
        unit.translation.component = component
        unit.is_batch_update = True
        unit.update_extra_flags(flags[unit.pk], user)
        changed_ids.add(unit.pk)
        changed_sources.add(unit.source_unit_id or unit.pk)
        updated = True
    return updated


@regex_session()
# ruff: ignore[complex-structure, too-many-arguments]
def bulk_perform(
    user: User | None,
    unit_set: UnitQuerySet,
    *,
    query: str,
    target_state: int | str,
    add_flags: str | Flags,
    remove_flags: str | Flags,
    add_labels: QuerySet[Label],
    remove_labels: QuerySet[Label],
    project: Project | None,
    enforce_permissions: bool = True,
    components: QuerySet[Component] | list[Component] | None = None,
    add_translation_flags: str | Flags = "",
    remove_translation_flags: str | Flags = "",
    search: str = "",
    replacement: str = "",
    search_type: str = "text",
    affected_unit_ids: set[int] | None = None,
    affected_source_unit_ids: set[int] | None = None,
    expected_unit_snapshots: dict[int, EvaluatedUnitSnapshot] | None = None,
    preview: list[BulkUnitEdit] | None = None,
) -> int:
    if user is None:
        msg = "Bulk edits require an explicit actor."
        raise ValueError(msg)
    matching = unit_set.search(query, project=project)
    target_state = int(target_state)
    if target_state not in EDITABLE_STATES | {-1, STATE_EMPTY}:
        raise ValidationError(gettext("Invalid target state."))
    text_edit = BulkReplacement(search, replacement, search_type)
    if search and target_state == STATE_EMPTY:
        raise ValidationError(
            gettext("Choose either replacement or clearing translations.")
        )
    planner = partial(
        plan_bulk_unit,
        user=user,
        target_state=target_state,
        replacement=text_edit,
        add_flags=FlagsValidator(add_flags),
        remove_flags=FlagsValidator(remove_flags),
        add_translation_flags=FlagsValidator(add_translation_flags),
        remove_translation_flags=FlagsValidator(remove_translation_flags),
        add_labels={label.pk for label in add_labels},
        remove_labels={label.pk for label in remove_labels},
        enforce_permissions=enforce_permissions,
    )
    # Keep the complete selection stable, and exclude it from propagation so
    # each selected target is transformed independently exactly once.
    selected_ids = set(matching.values_list("pk", flat=True))
    if components is None:
        components = Component.objects.filter(
            pk__in=Unit.objects.filter(pk__in=selected_ids).values_list(
                "translation__component_id", flat=True
            )
        )
    preview_count = 0
    changed_ids: set[int] = set()
    changed_sources: set[int] = set()
    for component in components:
        with transaction.atomic(), source_operation(component):
            component_units = Unit.objects.filter(
                pk__in=selected_ids, translation__component=component
            )
            if preview is None and (
                add_flags or remove_flags or add_labels or remove_labels
            ):
                lock_bulk_sources(component_units)
            if target_state == STATE_APPROVED and expected_unit_snapshots is not None:
                component_units = exclude_stale_evaluations(
                    component_units, expected_unit_snapshots
                )
            units = component_units.order_by("pk").prefetch().prefetch_bulk()
            if add_labels or remove_labels:
                units = units.prefetch_related("source_unit__labels")
            if preview is None and (
                target_state != -1
                or search
                or add_translation_flags
                or remove_translation_flags
            ):
                units = units.select_for_update()
            planned = plan_bulk_units(
                units.iterator(chunk_size=BULK_EDIT_PREVIEW_LIMIT),
                planner,
                text_edit,
                user,
                target_state,
                enforce_permissions=enforce_permissions,
            )
            if preview is not None:
                for edit in planned:
                    if edit.changed:
                        preview_count += 1
                        if len(preview) < BULK_EDIT_PREVIEW_LIMIT:
                            preview.append(edit)
                continue
            edits = list(planned)
            component.start_batched_checks()
            state_updates = []
            changes = []
            component_changed = False
            for edit in edits:
                unit = edit.unit
                unit.translation.component = component
                if edit.state is None:
                    continue
                if edit.target is not None or target_state == STATE_EMPTY:
                    saved = unit.translate(
                        user,
                        edit.target
                        if edit.target is not None
                        else unit.get_target_plurals(),
                        StringState(edit.state),
                        author=user,
                        change_action=ActionEvents.REPLACE
                        if search
                        else ActionEvents.BULK_EDIT,
                        select_for_update=False,
                        propagation_exclude_ids=selected_ids,
                    )
                    if not saved:
                        continue
                else:
                    unit.state = edit.state
                    unit.automatically_translated = False
                    changes.append(
                        unit.generate_change(
                            user,
                            user,
                            ActionEvents.BULK_EDIT,
                            check_new=False,
                            save=False,
                        )
                    )
                    state_updates.append(unit)
                changed_ids.add(unit.pk)
                changed_sources.add(unit.source_unit_id or unit.pk)
                component_changed = True
            Unit.objects.bulk_update(
                state_updates, ["state", "automatically_translated"], batch_size=500
            )
            Change.objects.bulk_create(changes, batch_size=500)
            PendingUnitChange.objects.bulk_create(
                [
                    PendingUnitChange.store_unit_change(
                        unit=unit, author=user, user=user, save=False
                    )
                    for unit in state_updates
                ],
                batch_size=500,
            )
            for unit in state_updates:
                propagate_parent_change(unit.translation, unit.pk, user)
                if unit.is_source:
                    unit.is_batch_update = True
                    unit.source_unit_save()
            processed_sources = set()
            for edit in edits:
                unit = edit.unit
                source = unit.source_unit
                if source.pk not in processed_sources:
                    processed_sources.add(source.pk)
                    source.translation.component = component
                    source.is_batch_update = True
                    changed = False
                    if edit.source_flags is not None:
                        source.update_extra_flags(edit.source_flags, user)
                        changed = True
                    for label_ids, action in (
                        (edit.add_labels, ActionEvents.LABEL_ADD),
                        (edit.remove_labels, ActionEvents.LABEL_REMOVE),
                    ):
                        if not label_ids:
                            continue
                        labels = list(
                            source.translation.component.project.label_set.filter(
                                pk__in=label_ids
                            )
                        )
                        if action == ActionEvents.LABEL_ADD:
                            source.labels.add(*labels)
                        else:
                            source.labels.remove(*labels)
                        for label in labels:
                            source.change_set.create(
                                action=action,
                                user=user,
                                author=user,
                                details={"label": label.name},
                            )
                        changed = True
                    if changed:
                        changed_ids.add(source.pk)
                        changed_sources.add(source.pk)
                        component_changed = True
            if apply_bulk_translation_flags(
                user, component, edits, changed_ids, changed_sources
            ):
                component_changed = True
        if preview is None and component_changed:
            component.invalidate_cache()
            component.run_batched_checks()
    if affected_unit_ids is not None:
        affected_unit_ids.update(changed_ids)
    if affected_source_unit_ids is not None:
        affected_source_unit_ids.update(changed_sources)
    return preview_count if preview is not None else len(changed_ids)
