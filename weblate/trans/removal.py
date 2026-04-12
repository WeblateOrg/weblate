# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from weblate.utils.stats import BaseStats

CURRENT_REMOVAL_BATCH: ContextVar[RemovalBatch | None] = ContextVar(
    "current_removal_batch", default=None
)


class RemovalBatch:
    def __init__(self) -> None:
        self.removed_component_ids: set[int] = set()
        self.stats_to_update: dict[str, BaseStats] = {}
        self.linked_components_to_refresh: set[int] = set()

    def mark_component(self, component_id: int) -> None:
        self.removed_component_ids.add(component_id)

    def collect_stats(self, stats_objects: Iterable[BaseStats]) -> None:
        for stats in stats_objects:
            self.stats_to_update[stats.cache_key] = stats

    def collect_linked_component(self, component_id: int | None) -> None:
        if component_id is not None:
            self.linked_components_to_refresh.add(component_id)

    def flush(self) -> None:
        from weblate.trans.models import Component  # noqa: PLC0415
        from weblate.utils.stats import GlobalStats, ProjectStats  # noqa: PLC0415

        regular_stats: list[BaseStats] = []
        project_stats: list[BaseStats] = []
        global_stats: list[BaseStats] = []

        for stats in self.stats_to_update.values():
            if isinstance(stats, GlobalStats):
                global_stats.append(stats)
            elif isinstance(stats, ProjectStats):
                project_stats.append(stats)
            else:
                regular_stats.append(stats)

        for stats in (*regular_stats, *project_stats, *global_stats):
            stats.update_stats()

        for component in Component.objects.filter(
            pk__in=self.linked_components_to_refresh
        ):
            component.update_alerts()


def get_current_removal_batch() -> RemovalBatch | None:
    return CURRENT_REMOVAL_BATCH.get()


@contextmanager
def removal_batch_context(batch: RemovalBatch) -> Iterator[None]:
    token = CURRENT_REMOVAL_BATCH.set(batch)
    try:
        yield
    finally:
        CURRENT_REMOVAL_BATCH.reset(token)
