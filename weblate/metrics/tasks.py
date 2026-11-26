# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from itertools import batched
from typing import TYPE_CHECKING

from celery.schedules import crontab
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.metrics.aggregation import BATCH_SIZE
from weblate.metrics.models import ContributorCollection, Metric
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.utils.celery import app
from weblate.utils.lock import AdvisoryLock, LockScope, WeblateLockTimeoutError
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from celery import Celery

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
    for batch in batched(
        Project.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        batch_started = time.monotonic()
        Metric.objects.collect_batch(batch, collection_date)
        count += len(batch)
        LOGGER.debug(
            "Collected %d project metrics in %.2f seconds",
            len(batch),
            time.monotonic() - batch_started,
        )
    _log_finished("project", collection_date, count, started)


@app.task(trail=False)
def collect_workspace_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting workspace metrics for %s", collection_date)
    count = 0
    for batch in batched(
        Workspace.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        batch_started = time.monotonic()
        Metric.objects.collect_batch(batch, collection_date)
        count += len(batch)
        LOGGER.debug(
            "Collected %d workspace metrics in %.2f seconds",
            len(batch),
            time.monotonic() - batch_started,
        )
    _log_finished("workspace", collection_date, count, started)


@app.task(trail=False)
def collect_category_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting category metrics for %s", collection_date)
    count = 0
    for batch in batched(
        Category.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        batch_started = time.monotonic()
        Metric.objects.collect_batch(batch, collection_date)
        count += len(batch)
        LOGGER.debug(
            "Collected %d category metrics in %.2f seconds",
            len(batch),
            time.monotonic() - batch_started,
        )
    _log_finished("category", collection_date, count, started)


@app.task(trail=False)
def collect_component_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting component metrics for %s", collection_date)
    count = 0
    for batch in batched(
        Component.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        batch_started = time.monotonic()
        Metric.objects.collect_batch(batch, collection_date)
        count += len(batch)
        LOGGER.debug(
            "Collected %d component metrics in %.2f seconds",
            len(batch),
            time.monotonic() - batch_started,
        )
    _log_finished("component", collection_date, count, started)


@app.task(trail=False)
def collect_component_list_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting component list metrics for %s", collection_date)
    count = 0
    for batch in batched(
        ComponentList.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        batch_started = time.monotonic()
        Metric.objects.collect_batch(batch, collection_date)
        count += len(batch)
        LOGGER.debug(
            "Collected %d component_list metrics in %.2f seconds",
            len(batch),
            time.monotonic() - batch_started,
        )
    _log_finished("component list", collection_date, count, started)


@app.task(
    trail=False,
    autoretry_for=(IntegrityError, OperationalError, WeblateLockTimeoutError),
    max_retries=12,
    retry_backoff=60,
)
def collect_translation_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    scope = LockScope.CONTRIBUTOR_METRICS
    lock = AdvisoryLock((scope.value, 0), scope=scope.label, timeout=0)
    with lock:
        collection: ContributorCollection | None
        collection, _created = ContributorCollection.objects.get_or_create(
            pk=1, defaults={"collection_date": collection_date}
        )
        if collection.last_completed == collection_date:
            return
        if collection_date < collection.collection_date:
            # Historical metrics can still be filled without changing the rankings.
            collection = None
        elif collection_date > collection.collection_date:
            collection.collection_date = collection_date
            collection.cursor = 0
            collection.save(update_fields=["collection_date", "cursor"])

        cursor = collection.cursor if collection else 0
        LOGGER.info(
            "Collecting translation metrics for %s after ID %d", collection_date, cursor
        )
        count = 0
        translations = Translation.objects.filter(pk__gt=cursor).order_by("pk")
        for batch in batched(translations.iterator(chunk_size=BATCH_SIZE), BATCH_SIZE):
            batch_started = time.monotonic()
            with transaction.atomic():
                Metric.objects.collect_batch(
                    batch, collection_date, refresh_contributors=collection is not None
                )
                if collection:
                    collection.cursor = batch[-1].pk
                    collection.save(update_fields=["cursor"])
            count += len(batch)
            LOGGER.debug(
                "Collected %d translation metrics through ID %d in %.2f seconds",
                len(batch),
                batch[-1].pk,
                time.monotonic() - batch_started,
            )
        if collection:
            collection.last_completed = collection_date
            collection.save(update_fields=["last_completed"])
        _log_finished("translation", collection_date, count, started)


@app.task(trail=False)
def collect_user_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting user metrics for %s", collection_date)
    count = 0
    user_ids = User.objects.order_by("pk").values_list("pk", flat=True)
    for batch in batched(user_ids.iterator(chunk_size=500), 500):
        Metric.objects.collect_users(batch, collection_date)
        count += len(batch)
    _log_finished("user", collection_date, count, started)


@app.task(trail=False)
def collect_language_metrics(date_value: str) -> None:
    collection_date = _parse_date(date_value)
    started = time.monotonic()
    LOGGER.info("Collecting language metrics for %s", collection_date)
    count = 0
    for batch in batched(
        Language.objects.order_by("pk").iterator(chunk_size=BATCH_SIZE), BATCH_SIZE
    ):
        batch_started = time.monotonic()
        Metric.objects.collect_batch(batch, collection_date)
        count += len(batch)
        LOGGER.debug(
            "Collected %d language metrics in %.2f seconds",
            len(batch),
            time.monotonic() - batch_started,
        )
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
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=1), collect_metrics.s(), name="collect-metrics"
    )
    sender.add_periodic_task(
        crontab(hour=23, minute=1), cleanup_metrics.s(), name="cleanup-metrics"
    )
