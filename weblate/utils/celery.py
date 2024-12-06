# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Celery integration helper tools."""

from __future__ import annotations

import os
import time
from collections import defaultdict

from celery import Celery
from celery.signals import after_setup_logger, task_failure
from django.conf import settings
from django.core.cache import cache
from django.core.checks import run_checks

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

app = Celery("weblate")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@task_failure.connect
def handle_task_failure(exception=None, **kwargs) -> None:
    from weblate.utils.errors import report_error

    report_error(
        "Failure while executing task",
        skip_sentry=True,
        print_tb=True,
        level="error",
    )


@app.on_after_configure.connect
def configure_error_handling(sender, **kargs) -> None:
    """Rollbar and Sentry integration."""
    from weblate.utils.errors import init_error_collection

    init_error_collection(celery=True)


@after_setup_logger.connect
def show_failing_system_check(sender, logger, **kwargs) -> None:
    if settings.DEBUG:
        for check in run_checks(include_deployment_checks=True):
            # Skip silenced checks and Celery one
            # (it fails when started from Celery startup)
            if check.is_silenced() or check.id == "weblate.E019":
                continue
            logger.warning("%s", check)


def get_queue_length(queue="celery"):
    with app.connection_or_acquire() as conn:
        return conn.default_channel.queue_declare(
            queue=queue, durable=True, auto_delete=False
        ).message_count


def get_queue_list():
    """List queues in Celery."""
    result = {"celery"}
    for route in settings.CELERY_TASK_ROUTES.values():
        if "queue" in route:
            result.add(route["queue"])
    return result


def get_queue_stats():
    """Calculate queue stats."""
    return {queue: get_queue_length(queue) for queue in get_queue_list()}


def get_task_progress(task):
    """Return progress of a Celery task."""
    # Completed task
    if task.ready():
        return 100
    # In progress
    result = task.result
    if task.state == "PROGRESS" and result is not None:
        return result["progress"]

    # Not yet started
    return 0


def is_celery_queue_long():
    """
    Check whether celery queue is too long.

    It does trigger if it is too long for at least one hour. This way peaks are
    filtered out, and no warning need be issued for big operations (for example
    site-wide autotranslation).
    """
    from weblate.trans.models import Translation

    cache_key = "celery_queue_stats"
    queues_data = cache.get(cache_key, {})

    # Hours since epoch
    current_hour = int(time.time() / 3600)
    test_hour = current_hour - 1

    # Fetch current stats
    stats = get_queue_stats()

    # Update counters
    if current_hour not in queues_data:
        # Delete stale items
        for key in list(queues_data.keys()):
            if key < test_hour:
                del queues_data[key]
        # Add current one
        queues_data[current_hour] = stats

        # Store to cache
        cache.set(cache_key, queues_data, 7200)

    # Do not fire if we do not have counts for two hours ago
    if test_hour not in queues_data:
        return False

    # Check if any queue got bigger
    base = queues_data[test_hour]
    thresholds: dict[str, int] = defaultdict(lambda: 50)
    # Set the limit to avoid trigger on auto-translating all components
    # nightly.
    thresholds["translate"] = max(1000, Translation.objects.count() // 30)
    return any(
        stat > thresholds[key] and base.get(key, 0) > thresholds[key]
        for key, stat in stats.items()
    )
