# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from celery.schedules import crontab
from django.utils import timezone

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.metrics.models import Metric
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.utils.celery import app
from weblate.utils.stats import iter_prefetch_stats
from weblate.workspaces.models import Workspace

LOGGER = logging.getLogger("weblate.metrics")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _log_finished(
    scope: str, collection_date: date, count: int, started: float
) -> None:
    LOGGER.info(
        "Collected %d %s metrics for %s in %.2f seconds",
        count,
        scope,
        collection_date,
        time.monotonic() - started,
    )


@app.task(trail=False)
def collect_global_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting global metrics for %s", collection_date)
    Metric.objects.collect_global(collection_date)
    _log_finished("global", collection_date, 1, started)


@app.task(trail=False)
def collect_project_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting project metrics for %s", collection_date)
    count = 0
    for project in iter_prefetch_stats(Project.objects.all()):
        Metric.objects.collect_project(project, collection_date)
        count += 1
    _log_finished("project", collection_date, count, started)


@app.task(trail=False)
def collect_workspace_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting workspace metrics for %s", collection_date)
    count = 0
    for workspace in iter_prefetch_stats(Workspace.objects.all()):
        Metric.objects.collect_workspace(workspace, collection_date)
        count += 1
    _log_finished("workspace", collection_date, count, started)


@app.task(trail=False)
def collect_category_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting category metrics for %s", collection_date)
    count = 0
    for category in iter_prefetch_stats(Category.objects.all()):
        Metric.objects.collect_category(category, collection_date)
        count += 1
    _log_finished("category", collection_date, count, started)


@app.task(trail=False)
def collect_component_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting component metrics for %s", collection_date)
    count = 0
    for component in iter_prefetch_stats(Component.objects.all()):
        Metric.objects.collect_component(component, collection_date)
        count += 1
    _log_finished("component", collection_date, count, started)


@app.task(trail=False)
def collect_component_list_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting component list metrics for %s", collection_date)
    count = 0
    for component_list in iter_prefetch_stats(ComponentList.objects.all()):
        Metric.objects.collect_component_list(component_list, collection_date)
        count += 1
    _log_finished("component list", collection_date, count, started)


@app.task(trail=False)
def collect_translation_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting translation metrics for %s", collection_date)
    count = 0
    for translation in iter_prefetch_stats(Translation.objects.all()):
        Metric.objects.collect_translation(translation, collection_date)
        count += 1
    _log_finished("translation", collection_date, count, started)


@app.task(trail=False)
def collect_user_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting user metrics for %s", collection_date)
    count = 0
    for user in User.objects.all().iterator(chunk_size=500):
        Metric.objects.collect_user(user, collection_date)
        count += 1
    _log_finished("user", collection_date, count, started)


@app.task(trail=False)
def collect_language_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting language metrics for %s", collection_date)
    count = 0
    for language in iter_prefetch_stats(Language.objects.all()):
        Metric.objects.collect_language(language, collection_date)
        count += 1
    _log_finished("language", collection_date, count, started)


METRIC_COLLECTION_TASKS = (
    collect_global_metrics,
    collect_project_metrics,
    collect_workspace_metrics,
    collect_category_metrics,
    collect_component_metrics,
    collect_component_list_metrics,
    collect_translation_metrics,
    collect_user_metrics,
    collect_language_metrics,
)


@app.task(trail=False)
def collect_metrics() -> None:
    """Schedule independent metric collection tasks for each scope."""
    date_value = timezone.now().date().isoformat()
    for task in METRIC_COLLECTION_TASKS:
        task.delay(date_value)


@app.task(trail=False)
def cleanup_metrics() -> None:
    """Remove stale metrics."""
    today = timezone.now().date()
    # Remove past metrics, but we need data for last 24 months
    Metric.objects.filter(date__lte=today - timedelta(days=800)).delete()

    # Remove detailed data for past metrics, we need details only for two months
    # - avoid filtering on data field as that one is not indexed
    # - wipe only interval of data with assumption that this task is executed daily
    Metric.objects.filter(
        date__range=(today - timedelta(days=75), today - timedelta(days=65))
    ).update(data=None)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
    sender.add_periodic_task(
        crontab(hour=23, minute=1), cleanup_metrics.s(), name="cleanup-metrics"
    )
