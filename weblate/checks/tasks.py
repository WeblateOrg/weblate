# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Value
from django.db.models.functions import MD5, Lower

from weblate.checks.base import BatchCheckMixin
from weblate.checks.models import CHECKS, Check
from weblate.trans.models import Component, Project, Unit
from weblate.trans.util import split_plural
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError

if TYPE_CHECKING:
    from weblate.trans.models import Translation
    from weblate.trans.models.unit import UnitQuerySet


class PropagatedCheckGroup(TypedDict):
    check: str
    scope: Literal["source", "target"]
    source_language_id: int | None
    language_id: int
    plural_id: int
    source: str
    context: str
    target: str
    source_rules: NotRequired[tuple[int, str, int]]


@dataclass
class PendingCheckRefresh:
    """Collect refreshes within one savepoint without retaining model instances."""

    project_id: int
    groups: list[PropagatedCheckGroup] = field(default_factory=list)
    group_keys: set[tuple[object, ...]] = field(default_factory=set)
    unit_ids: set[int] = field(default_factory=set)

    def __call__(self) -> None:
        refresh_propagated_checks.delay(
            self.project_id, self.groups, sorted(self.unit_ids)
        )


def schedule_propagated_checks(
    unit: Unit, checks: set[str], *, refresh_unit: bool = False
) -> None:
    component = unit.translation.component
    connection = transaction.get_connection()
    pending = None
    # Never merge into an outer savepoint's callback: a rollback of the inner
    # savepoint must discard its refreshes as well as its changes.
    for savepoints, callback, _robust in connection.run_on_commit:
        if (
            savepoints == set(connection.savepoint_ids)
            and isinstance(callback, PendingCheckRefresh)
            and callback.project_id == component.project_id
        ):
            pending = callback
            break
    if pending is None:
        pending = PendingCheckRefresh(component.project_id)
    if refresh_unit:
        pending.unit_ids.add(unit.pk)

    custom_sources = bool(component.project.translation_parent_language_ids)
    for check in sorted(checks):
        scope = CHECKS[check].propagates
        if scope is None:
            continue
        states = [
            {
                "source": unit.old_unit["source"],
                "context": unit.old_unit["context"],
                "target": unit.old_unit["target"],
            },
            {"source": unit.source, "context": unit.context, "target": unit.target},
        ]
        for state in states:
            group: PropagatedCheckGroup = {
                "check": check,
                "scope": scope,
                "source_language_id": component.source_language_id,
                "language_id": unit.translation.language_id,
                "plural_id": unit.translation.plural_id,
                "source": state.get("source", unit.source),
                "context": state.get("context", unit.context),
                "target": state.get("target", unit.target),
            }
            if custom_sources:
                group["source_language_id"] = unit.effective_source_language.pk
                plural = unit.effective_source_plural
                group["source_rules"] = (plural.number, plural.formula, plural.type)
                if unit.translation_parent_id or unit.missing_source_snapshot:
                    group["source"] = unit.effective_source
            if scope == "source":
                group["target"] = ""
            else:
                if not any(split_plural(group["target"])):
                    continue
                group["source"] = group["context"] = ""
                # Target groups are shared by translations with the same plural.
                group["language_id"] = 0
            key = tuple(group.values())
            if key not in pending.group_keys:
                pending.group_keys.add(key)
                pending.groups.append(group)
    if (pending.groups or pending.unit_ids) and not any(
        callback is pending for _, callback, _ in connection.run_on_commit
    ):
        transaction.on_commit(pending)


@transaction.atomic
def _store_propagated_checks(
    check_id: str, create: list[Check], remove: list[int]
) -> None:
    create.sort(key=lambda check: (check.unit_id, check.name))
    Check.objects.bulk_create(create, batch_size=500, ignore_conflicts=True)
    Check.objects.filter(unit_id__in=remove, name=check_id).delete()


def _get_propagated_check_units(
    project_id: int, group: PropagatedCheckGroup, *, custom_sources: bool
) -> UnitQuerySet:
    """Find peers sharing the check's effective source or target context."""
    units = (
        Unit.objects.exclude_blocked(custom_sources=custom_sources)
        .with_effective_source(custom_sources=custom_sources, select=False)
        .filter(
            translation__component__project_id=project_id,
            check_source_language=group["source_language_id"],
            translation__component__allow_translation_propagation=True,
            translation__plural_id=group["plural_id"],
        )
    )
    if custom_sources and "source_rules" in group:
        number, formula, plural_type = group["source_rules"]
        units = units.filter(
            check_source_number=number,
            check_source_formula=formula,
            check_source_type=plural_type,
        )
    if group["scope"] == "source":
        units = units.filter(
            translation__language_id=group["language_id"],
            check_source=group["source"],
            context=group["context"],
            check_source__lower__md5=MD5(Lower(Value(group["source"]))),
            context__lower__md5=MD5(Lower(Value(group["context"]))),
        )
    else:
        units = units.filter(
            target=group["target"],
            target__lower__md5=MD5(Lower(Value(group["target"]))),
        )
    return units.prefetch().prefetch_source().prefetch_all_checks()


@app.task(
    trail=False,
    autoretry_for=(
        WeblateLockTimeoutError,
        OperationalError,
        IntegrityError,
        ObjectDoesNotExist,
    ),
    retry_backoff=60,
)
def refresh_propagated_checks(
    project_id: int,
    groups: list[PropagatedCheckGroup],
    unit_ids: list[int] | None = None,
) -> None:
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return
    # Commit warning changes in chunks so the worker does not hold row locks
    # for the entire group and block concurrent translation saves.
    with project.checks_lock:
        project.log_info("refreshing %d propagated check groups", len(groups))
        custom_sources = bool(project.translation_parent_language_ids)
        translations: dict[int, Translation] = {}
        sources: set[int] = set()
        # Text propagation has already changed these units' content. They need
        # their own checks updated, in addition to related propagated warnings.
        if unit_ids:
            for unit in (
                Unit.objects.filter(
                    pk__in=unit_ids, translation__component__project_id=project_id
                )
                .prefetch()
                .prefetch_source()
                .prefetch_all_checks()
                .iterator(chunk_size=500)
            ):
                with transaction.atomic():
                    unit.is_batch_update = True
                    unit.run_checks(skip_propagate=True)
                translations[unit.translation_id] = unit.translation
                if unit.source_unit_id is not None:
                    sources.add(unit.source_unit_id)
        for group in groups:
            check = CHECKS.get(group["check"])
            if check is None or check.propagates != group["scope"]:
                continue
            if check.propagates == "target" and not any(split_plural(group["target"])):
                continue
            units = _get_propagated_check_units(
                project_id, group, custom_sources=custom_sources
            )
            create = []
            remove = []
            for unit, failed in check.evaluate_propagated(units):
                # Also repair derived source warnings and stats on a retry
                # after an earlier attempt committed only some chunks.
                translations[unit.translation_id] = unit.translation
                if not unit.is_source and unit.source_unit_id is not None:
                    sources.add(unit.source_unit_id)
                existing = check.check_id in unit.all_checks_names
                if existing == failed:
                    continue
                if failed:
                    create.append(Check(unit_id=unit.pk, name=check.check_id))
                else:
                    remove.append(unit.pk)
                if len(create) + len(remove) >= 500:
                    _store_propagated_checks(check.check_id, create, remove)
                    create = []
                    remove = []
            _store_propagated_checks(check.check_id, create, remove)
        for source in (
            Unit.objects.filter(pk__in=sources)
            .prefetch()
            .prefetch_all_checks()
            .iterator(chunk_size=500)
        ):
            with transaction.atomic():
                source.is_batch_update = True
                source.run_checks(skip_propagate=True)
            translations[source.translation_id] = source.translation
        with transaction.atomic():
            for translation in translations.values():
                translation.require_full_stats_rebuild()
                translation.invalidate_cache()


def _perform_batched_checks(component: Component, checks: list[str]) -> None:
    for check in sorted(checks, key=lambda check_id: check_id in CHECKS.source):
        check_obj = CHECKS[check]
        if not isinstance(check_obj, BatchCheckMixin):
            msg = (
                f"Check {check!r} with type {type(check_obj).__name__} "
                "does not support batch updates"
            )
            raise TypeError(msg)
        component.log_info("batch updating check %s", check)
        check_obj.perform_batch(component)


def _run_component_checks(component: Component, unit_ids: list[int]) -> None:
    with transaction.atomic():
        if unit_ids:
            source_translation = component.get_source_translation()
            if source_translation is not None:
                units = source_translation.unit_set.filter(
                    pk__in=unit_ids
                ).prefetch_all_checks()
                unit_count = units.count()
                component.log_info("running source checks for %d strings", unit_count)
                for unit in units.iterator(chunk_size=500):
                    unit.translation.component = component
                    unit.is_batch_update = True
                    unit.run_checks()
        if component.batched_checks:
            _perform_batched_checks(component, list(component.batched_checks))


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=60,
)
def finalize_component_checks(
    component_id: int,
    unit_ids: list[int],
    checks: list[str],
    *,
    batch_mode: bool,
    component: Component | None = None,
) -> None:
    if not unit_ids and not checks:
        return
    if component is None:
        try:
            component = Component.objects.get(pk=component_id)
        except Component.DoesNotExist:
            return
    with component.checks_lock:
        component.batch_checks = batch_mode
        component.batched_checks = set(checks)
        try:
            _run_component_checks(component, unit_ids)
        finally:
            component.batch_checks = False
            component.batched_checks = set()
        component.invalidate_cache()
