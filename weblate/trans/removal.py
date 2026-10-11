# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING

from celery import current_task
from django.db import transaction

from weblate.logger import LOGGER

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable

    from weblate.trans.models import Category, Component, Project
    from weblate.utils.stats import BaseStats

CURRENT_REMOVAL_BATCH: ContextVar[RemovalBatch | None] = ContextVar(
    "current_removal_batch", default=None
)


def logged_removal(model: type[Component | Category | Project]) -> Callable:
    """Log filesystem-independent outcomes around the removal transaction."""

    def decorate(function: Callable[..., None]) -> Callable[..., None]:
        @wraps(function)
        def wrapped(pk: int, uid: int | None, *args: object, **kwargs: object) -> None:
            instance = model.objects.filter(pk=pk).first()
            if instance is None:
                LOGGER.info(
                    "%s removal skipped: id=%s already missing", model.__name__, pk
                )
                return None
            identity = {
                "model": model.__name__,
                "id": pk,
                "slug": instance.full_slug,
                "actor_id": uid,
                "task_id": current_task.request.id if current_task else None,
            }
            committed = False

            def log_commit() -> None:
                nonlocal committed
                committed = True
                LOGGER.info("removal committed: %s", identity)

            LOGGER.info("removal started: %s", identity)
            try:
                with transaction.atomic():
                    # Run before follow-ups, so their failures cannot look like rollback.
                    transaction.on_commit(log_commit)
                    return function(pk, uid, *args, **kwargs)
            except Exception:
                LOGGER.exception(
                    "removal %s: %s",
                    "follow-up failed after commit"
                    if committed
                    else "failed before commit",
                    identity,
                )
                raise

        return wrapped

    return decorate


class RemovalBatch:
    def __init__(self) -> None:
        self.removed_component_ids: set[int] = set()
        self.stats_to_update: dict[str, BaseStats] = {}
        self.components_to_refresh: set[int] = set()
        self.billings_to_refresh: set[int] = set()

    def mark_component(self, component_id: int) -> None:
        self.removed_component_ids.add(component_id)

    def collect_stats(self, stats_objects: Iterable[BaseStats]) -> None:
        for stats in stats_objects:
            self.stats_to_update[stats.cache_key] = stats

    def collect_linked_component(self, component_id: int | None) -> None:
        self.collect_alert_update(component_id)

    def collect_alert_update(self, component_id: int | None) -> None:
        if component_id is not None:
            self.components_to_refresh.add(component_id)

    def collect_billing_alert_update(self, billing_id: int) -> None:
        self.billings_to_refresh.add(billing_id)

    def flush(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Component
        from weblate.utils.stats import (  # ruff: ignore[import-outside-top-level]
            update_stats_objects,
        )

        update_stats_objects(self.stats_to_update.values())

        if self.billings_to_refresh:
            from weblate.billing.models import Billing  # ruff: ignore[import-outside-top-level]

            for billing in Billing.objects.filter(pk__in=self.billings_to_refresh):
                billing.update_alerts()

        for component in Component.objects.filter(
            pk__in=self.components_to_refresh
        ).exclude(pk__in=self.removed_component_ids):
            component.update_alerts()


def get_current_removal_batch() -> RemovalBatch | None:
    return CURRENT_REMOVAL_BATCH.get()


def defer_alert_update(component_id: int | None) -> bool:
    """Defer recalculation until removal commits, using fresh component state."""
    batch = get_current_removal_batch()
    if batch is None:
        return False
    batch.collect_alert_update(component_id)
    return True


def is_removed_component(component_id: int | None) -> bool:
    """Whether alert mutations target a component being removed."""
    batch = get_current_removal_batch()
    return batch is not None and (
        component_id is None or component_id in batch.removed_component_ids
    )


@contextmanager
def removal_batch_context(batch: RemovalBatch) -> Generator[None, None, None]:
    token = CURRENT_REMOVAL_BATCH.set(batch)
    try:
        yield
    finally:
        CURRENT_REMOVAL_BATCH.reset(token)
