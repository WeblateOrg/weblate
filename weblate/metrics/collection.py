# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Batch preparation, separate from metric persistence and SQL aggregation."""

from __future__ import annotations

from itertools import batched
from typing import TYPE_CHECKING

from django.core.cache import cache

from weblate.lang.models import Language
from weblate.metrics.aggregation import BATCH_SIZE, counters, history, language_pairs
from weblate.metrics.models import (
    BASIC_KEYS,
    SOURCE_KEYS,
    Metric,
    serialize_metric_data,
)
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage, prefetch_stats
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Sequence

    from weblate.metrics.models import MetricManager

MetricObject = (
    Project | Category | Workspace | Component | ComponentList | Translation | Language
)


def prepare_metric(
    obj: MetricObject | ProjectLanguage | CategoryLanguage,
    data: dict,
    scope: int,
    date: dt.date,
    secondary: int = 0,
    relation: int | None = None,
) -> Metric:
    keys = BASIC_KEYS if scope == Metric.SCOPE_TRANSLATION else SOURCE_KEYS
    for key in keys:
        data[key] = getattr(obj.stats, key)
    changes, serialized = serialize_metric_data(data)
    if relation is None:
        if isinstance(obj, Workspace):
            relation = obj.metric_id
        elif isinstance(obj, ProjectLanguage):
            relation = obj.project.pk
        elif isinstance(obj, CategoryLanguage):
            relation = obj.category.pk
        else:
            relation = obj.pk
    return Metric(
        scope=scope,
        relation=relation,
        secondary=secondary,
        date=date,
        changes=changes,
        data=serialized,
    )


def collect_batch(
    manager: MetricManager, objects: Sequence[MetricObject], date: dt.date
) -> None:
    """Collect at most one batch of homogeneous objects, plus bounded language batches."""
    if not objects:
        return
    if len(objects) > BATCH_SIZE:
        msg = "Metric collection batch exceeds its limit"
        raise ValueError(msg)
    scope, scope_id = {
        Project: ("project", Metric.SCOPE_PROJECT),
        Category: ("category", Metric.SCOPE_CATEGORY),
        Workspace: ("workspace", Metric.SCOPE_WORKSPACE),
        Component: ("component", Metric.SCOPE_COMPONENT),
        ComponentList: ("component_list", Metric.SCOPE_COMPONENT_LIST),
        Translation: ("translation", Metric.SCOPE_TRANSLATION),
        Language: ("language", Metric.SCOPE_LANGUAGE),
    }[type(objects[0])]
    ids = [obj.pk for obj in objects]
    changes = history(scope, ids, date, manager.db)
    counts = counters(scope, ids, manager.db)
    prefetch_stats(objects)
    accounting_keys = []
    accounting = {}
    if scope == "project":
        accounting_keys = [
            f"machinery-accounting:{kind}:{pk}"
            for pk in ids
            for kind in ("internal", "external")
        ]
        accounting = cache.get_many(accounting_keys)
    metrics = []
    for obj in objects:
        data = {"changes": 0, "contributors": 0, "contributors_total": 0}
        data.update(changes.get(obj.pk, {}))
        data.update(counts[obj.pk])
        if scope == "project":
            for kind in ("internal", "external"):
                key = f"machinery-accounting:{kind}:{obj.pk}"
                if key in accounting:
                    data[f"machinery:{kind}"] = accounting[key]
        metrics.append(prepare_metric(obj, data, scope_id, date))
    if scope in {"project", "category"}:
        collect_languages(manager, objects, scope, date)
    if accounting_keys:
        cache.delete_many(accounting_keys)
    manager.store_batch(metrics)


def collect_languages(
    manager: MetricManager, objects: Sequence, scope: str, date: dt.date
) -> None:
    parents = {obj.pk: obj for obj in objects}
    for pairs in batched(language_pairs(scope, list(parents), manager.db), BATCH_SIZE):
        languages = Language.objects.using(manager.db).in_bulk(
            {pair[1] for pair in pairs}
        )
        wrapper = ProjectLanguage if scope == "project" else CategoryLanguage
        wrappers = [
            wrapper(parents[parent], languages[language]) for parent, language in pairs
        ]
        prefetch_stats(wrappers)
        changes = history(scope, list(parents), date, manager.db, pairs)
        scope_id = (
            Metric.SCOPE_PROJECT_LANGUAGE
            if scope == "project"
            else Metric.SCOPE_CATEGORY_LANGUAGE
        )
        metrics = []
        for obj, pair in zip(wrappers, pairs, strict=True):
            data = {"changes": 0, "contributors": 0, "contributors_total": 0}
            data.update(changes.get(pair, {}))
            # Language wrappers have a composite string pk; stored relations use
            # the parent id and the language id instead.
            metric = prepare_metric(obj, data, scope_id, date, pair[1], pair[0])
            metrics.append(metric)
        manager.store_batch(metrics)
