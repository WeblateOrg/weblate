# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Opt-in metrics benchmark, using only pytest's disposable database.

Run with WEBLATE_METRICS_BENCHMARK=1 uv run pytest -n 1 -s
weblate/metrics/test_benchmark.py. The single-object baseline also runs on the
parent revision: copy this file there and set WEBLATE_METRICS_BASELINE=1.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import batched
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import skipUnless
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, models
from django.test import override_settings
from django.utils import timezone

from weblate.metrics.models import SOURCE_KEYS, Metric
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Category,
    Component,
    ComponentLink,
    ComponentList,
    Project,
    Translation,
)
from weblate.trans.models.change import Change
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.utils.stats import CategoryLanguage, ProjectLanguage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


@dataclass
class QueryRecorder:
    count: int = 0
    plans: dict[str, Sequence | dict | None] = field(default_factory=dict)

    def __call__(
        self,
        execute: Callable[..., object],
        sql: str,
        params: Sequence | dict | None,
        many: bool,
        context: dict[str, object],
    ) -> object:
        self.count += 1
        if "contributors_total" in sql or "COUNT(DISTINCT h.user_id)" in sql:
            self.plans.setdefault(sql, params)
        return execute(sql, params, many, context)


@skipUnless(os.environ.get("WEBLATE_METRICS_BENCHMARK"), "Opt-in scalability benchmark")
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "OPTIONS": {"MAX_ENTRIES": 100000},
        }
    }
)
class MetricsBenchmark(FixtureComponentTestCase):
    def test_large_site(self) -> None:
        projects = Project.objects.bulk_create(
            [
                Project(
                    name=f"Metrics benchmark {index}", slug=f"metrics-benchmark-{index}"
                )
                for index in range(2000)
            ]
        )
        categories = Category.objects.bulk_create(
            [
                Category(
                    project=projects[1 if index == 2 else 0],
                    name=f"Benchmark {index}",
                    slug=f"benchmark-{index}",
                )
                for index in range(4)
            ]
        )
        categories[1].category = categories[0]
        categories[1].save(update_fields=["category"])
        prototype = {
            field.attname: getattr(self.component, field.attname)
            for field in Component._meta.concrete_fields  # ruff: ignore[private-member-access]
            if not field.primary_key
        }
        components = []
        # One dense project plus one component per remaining project.
        for index in range(6999):
            values = {
                **prototype,
                "project_id": projects[0 if index < 5000 else index - 4999].pk,
                "slug": f"benchmark-{index}",
                "name": f"Benchmark {index}",
                "category_id": categories[1].pk if index < 5000 else None,
            }
            components.append(Component(**values))
        Component.objects.bulk_create(components, batch_size=500)
        translation_values = {
            field.attname: getattr(self.translation, field.attname)
            for field in Translation._meta.concrete_fields  # ruff: ignore[private-member-access]
            if not field.primary_key
        }
        translations = Translation.objects.bulk_create(
            [
                Translation(**{**translation_values, "component_id": component.pk})
                for component in components
            ],
            batch_size=500,
        )
        lists = ComponentList.objects.bulk_create(
            [
                ComponentList(name=f"Benchmark {index}", slug=f"benchmark-{index}")
                for index in range(4)
            ]
        )
        through = ComponentList.components.through
        for membership_rows in batched(
            (
                through(componentlist_id=clist.pk, component_id=component.pk)
                for clist in lists
                for component in components[:5000]
            ),
            500,
        ):
            through.objects.bulk_create(membership_rows)
        ComponentLink.objects.bulk_create(
            [
                ComponentLink(
                    component=component, project=projects[1], category=categories[2]
                )
                for component in components[:5000]
            ],
            batch_size=500,
        )
        # Synthetic rows bypass relationship fixup and notification dispatch.
        with patch.object(Change, "fixup_references"):
            for change_rows in batched(
                (
                    Change(
                        project_id=component.project_id,
                        component_id=component.pk,
                        category_id=component.category_id,
                        translation_id=translation.pk,
                        language_id=translation.language_id,
                        user=self.user,
                        action=ActionEvents.CHANGE,
                    )
                    for component, translation in zip(
                        components, translations, strict=True
                    )
                    for _ in range(20)
                ),
                500,
            ):
                models.QuerySet[Change, Change](
                    model=Change, using="default"
                ).bulk_create(change_rows)
        Change.objects.filter(component_id__in=[c.pk for c in components]).update(
            timestamp=timezone.now() - timedelta(days=1)
        )
        stats = dict.fromkeys(SOURCE_KEYS, 0)
        seed_objects: list[
            Project
            | Category
            | Component
            | Translation
            | ComponentList
            | ProjectLanguage
            | CategoryLanguage
        ] = [*projects, *categories, *components, *translations, *lists]
        wrappers: list[ProjectLanguage | CategoryLanguage] = [
            ProjectLanguage(project, self.translation.language) for project in projects
        ]
        wrappers += [
            CategoryLanguage(category, self.translation.language)
            for category in categories[:3]
        ]
        for stats_rows in batched([*seed_objects, *wrappers], 500):
            cache.set_many({obj.stats.cache_key: stats for obj in stats_rows})
        self.addCleanup(
            cache.delete_many,
            [obj.stats.cache_key for obj in [*seed_objects, *wrappers]],
        )
        del (
            seed_objects,
            wrappers,
            components,
            translations,
            prototype,
            translation_values,
        )
        gc.collect()

        baseline = bool(os.environ.get("WEBLATE_METRICS_BASELINE"))
        report = {}
        all_plans = []
        scopes: tuple[tuple[str, Sequence[Project | Category | ComponentList]], ...] = (
            ("project", projects),
            ("category", categories),
            ("component_list", lists),
        )
        for scope, scope_objects in scopes:
            recorder = QueryRecorder()

            Metric.objects.all().delete()
            tracemalloc.start()
            started = time.monotonic()
            with connection.execute_wrapper(recorder):
                if baseline:
                    for obj in scope_objects:
                        getattr(Metric.objects, f"collect_{scope}")(obj)
                else:
                    for metric_rows in batched(scope_objects, 500):
                        Metric.objects.collect_batch(metric_rows, timezone.now().date())
            elapsed = time.monotonic() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            report[scope] = {
                "seconds": elapsed,
                "queries": recorder.count,
                "peak_python_bytes": peak,
            }
            for sql, params in recorder.plans.items():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
                    )
                    all_plans.append({"scope": scope, "plan": cursor.fetchone()[0]})
        import resource  # ruff: ignore[import-outside-top-level]

        output = json.dumps(
            {
                "baseline": baseline,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "results": report,
                "plans": all_plans,
            }
        )
        if destination := os.environ.get("WEBLATE_METRICS_BENCHMARK_OUTPUT"):
            Path(destination).write_text(output + "\n", encoding="utf-8")
        else:
            sys.stdout.write(output + "\n")
