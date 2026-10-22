# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Celery integration helper tools."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import suppress
from copy import deepcopy
from functools import partial
from typing import TYPE_CHECKING, Any, cast

from celery import Celery
from celery.contrib.django.task import DjangoTask
from celery.signals import (
    after_setup_logger,
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
    worker_before_create_process,
)
from django.conf import settings
from django.core.cache import cache
from django.core.checks import run_checks
from django.db import DatabaseError, transaction
from django.utils.translation import gettext

from weblate.automation.context import automation_origin
from weblate.utils.change_origin import (
    ACTING_USER_HEADER,
    CHANGE_ORIGIN_HEADER,
    acting_user_context,
    capture_change_origin,
    change_origin,
    get_acting_user,
    get_change_origin,
)
from weblate.utils.task_log import record_task_failure

if TYPE_CHECKING:
    from weblate.auth.models import User


# Type annotation compatibility
# ruff: ignore[unused-lambda-argument]
Celery.__class_getitem__ = classmethod(lambda cls, *args, **kwargs: cls)
# ruff: ignore[unused-lambda-argument]
DjangoTask.__class_getitem__ = classmethod(lambda cls, *args, **kwargs: cls)

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings")

# Avoid loading the complete URL configuration and optional integrations in every
# Celery worker. Deployment checks are run separately during container startup and
# remain available through ``weblate check --deploy`` for other installations.
os.environ.setdefault("CELERY_SKIP_CHECKS", "1")


class OriginTask(DjangoTask):
    """Capture provenance before publication, including deferred and eager tasks."""

    # Celery's custom task base does not preserve individual task return types.
    # ruff: ignore[any-type]
    def __call__(self, *args: object, **kwargs: object) -> Any:
        # Resolve within execution, not a signal receiver: Celery logs receiver
        # exceptions and would otherwise continue executing with a missing actor.
        from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]

        headers = self.request.headers or {}
        user = (
            get_acting_user()
            if self.request.is_eager or self.request.called_directly
            else None
        )
        if ACTING_USER_HEADER in headers:
            user_id = headers[ACTING_USER_HEADER]
            if user_id is not None and (
                not isinstance(user_id, int)
                or isinstance(user_id, bool)
                or user_id <= 0
            ):
                msg = "Invalid task acting user ID"
                raise ValueError(msg)
            user = User.objects.get(pk=user_id) if user_id is not None else None
        with acting_user_context(user):
            if self.request.called_directly:
                return super().__call__(*args, **kwargs)
            # The worker/eager tracer already installed the execution request.
            # Task.__call__ would replace it, losing retry and header state.
            return self.run(*args, **kwargs)

    def apply_async(self, *args: object, **options: object):
        headers = dict(cast("dict[str, object] | None", options.get("headers")) or {})
        headers.setdefault(CHANGE_ORIGIN_HEADER, get_change_origin())
        user = get_acting_user()
        headers.setdefault(ACTING_USER_HEADER, user.pk if user is not None else None)
        options["headers"] = headers
        return super().apply_async(*cast("Any", args), **cast("Any", options))

    # celery-stubs incorrectly promises AsyncResult for the deferred methods.
    def delay_on_commit(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        transaction.on_commit(
            capture_change_origin(partial(self.delay, *args, **kwargs))
        )

    def apply_async_on_commit(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
        transaction.on_commit(
            capture_change_origin(partial(self.apply_async, *args, **kwargs))
        )


app = Celery[OriginTask]("weblate", task_cls=OriginTask)

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

TASK_METADATA_TTL = 6 * 3600


@worker_before_create_process.connect
def preload_urls_before_fork(**kwargs) -> None:
    """Load URL patterns in the parent process before forking a worker."""
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.startup import preload_url_patterns

    preload_url_patterns()


def get_task_metadata_key(task_id: str) -> str:
    return f"task-meta-{task_id}"


def store_task_metadata(
    task_id: str | None,
    *,
    component_id: int | None = None,
    component_ids: list[int] | None = None,
    translation_id: int | None = None,
    user_id: int | None = None,
    task_kind: str | None = None,
    failure_component_ids: list[int] | None = None,
    failure_repository_ids: list[int] | None = None,
    cancellable: bool = True,
) -> None:
    if not task_id:
        return
    from weblate.utils.lock import WeblateLock  # ruff: ignore[import-outside-top-level]

    # Publisher and worker updates must preserve each other's visibility metadata.
    with WeblateLock(scope="task-metadata", key=task_id, slug=task_id, timeout=10):
        existing = get_task_metadata(task_id)
        if existing is None:
            data: dict[str, Any] = {
                "component_id": component_id,
                "translation_id": translation_id,
            }
        else:
            data = existing.copy()
            if component_id is not None:
                data["component_id"] = component_id
            if translation_id is not None:
                data["translation_id"] = translation_id
        if component_ids is not None:
            data["component_ids"] = component_ids
        if user_id is not None:
            data["user_id"] = user_id
        if task_kind is not None:
            data["task_kind"] = task_kind
        if failure_component_ids is not None:
            data["failure_component_ids"] = failure_component_ids
        if failure_repository_ids is not None:
            data["failure_repository_ids"] = failure_repository_ids
        if not cancellable:
            data["cancellable"] = False
        cache.set(
            get_task_metadata_key(task_id),
            data,
            TASK_METADATA_TTL,
        )


def get_task_metadata(task_id: str) -> dict[str, Any] | None:
    return cache.get(get_task_metadata_key(task_id))


def filter_task_warnings(result: dict, user: User | None) -> dict:
    """Expose warning details only to readers of every named component."""
    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    public_result = {
        key: value for key, value in result.items() if key != "_warning_details"
    }
    warnings = result.get("warnings")
    if not isinstance(warnings, list):
        if "warnings" in result:
            public_result["warnings"] = [
                gettext("Automatic translation reported a warning.")
            ]
        return public_result
    details = result.get("_warning_details")
    validated: list[tuple[str, str, list[int]] | None] = []
    for index, warning in enumerate(warnings):
        detail = (
            details[index]
            if isinstance(details, list) and index < len(details)
            else None
        )
        if (
            isinstance(detail, dict)
            and isinstance(warning, str)
            and detail.get("message") == warning
            and isinstance(detail.get("public_message"), str)
            and isinstance(detail.get("component_ids"), list)
            and all(
                isinstance(pk, int) and not isinstance(pk, bool)
                for pk in detail["component_ids"]
            )
        ):
            validated.append(
                (warning, detail["public_message"], detail["component_ids"])
            )
        else:
            validated.append(None)
    ids = {pk for detail in validated if detail is not None for pk in detail[2]}
    accessible = (
        set(
            Component.objects.filter_access(user)
            .filter(pk__in=ids)
            .values_list("pk", flat=True)
        )
        if user is not None and ids
        else set()
    )
    visible_warnings = []
    for detail in validated:
        if detail is None:
            visible_warnings.append(
                gettext("Automatic translation reported a warning.")
            )
        elif user is not None and set(detail[2]).issubset(accessible):
            visible_warnings.append(detail[0])
        else:
            visible_warnings.append(detail[1])
    public_result["warnings"] = visible_warnings
    return public_result


def sanitize_task_result(
    task_id: str, result: object, user: User | None = None
) -> object:
    """Keep component task failure details in the permission-filtered log."""
    if not isinstance(result, (Exception, dict)):
        return result
    metadata = get_task_metadata(task_id) or {}
    if isinstance(result, dict) and "_automatic_translation_failed" in result:
        failed = result.get("_automatic_translation_failed") is True
        result = {
            key: value
            for key, value in result.items()
            if key != "_automatic_translation_failed"
        }
        if failed:
            result["message"] = gettext(
                "Automatic translation failed. See the task log for details."
            )
    if isinstance(result, dict) and (
        "_warning_details" in result
        or metadata.get("task_kind") == "automatic-translation"
    ):
        result = filter_task_warnings(result, user)
    if not any(
        metadata.get(key)
        for key in ("component_id", "component_ids", "translation_id", "task_kind")
    ):
        return result
    if isinstance(result, Exception):
        return gettext("Task could not be completed. See the task log for details.")
    completion_message = result.get("completion_message")
    if not isinstance(completion_message, dict) or not isinstance(
        completion_message.get("text"), str
    ):
        return result
    if metadata.get("task_kind") != "repository-operation":
        return result
    failed = result.get("result") is False or completion_message.get("level") == "error"
    text = (
        gettext("Repository operation completed with errors.")
        if failed
        else gettext("Repository operation completed.")
    )
    return {**result, "completion_message": {**completion_message, "text": text}}


def delete_task_metadata(task_id: str | None) -> None:
    if not task_id:
        return
    cache.delete(get_task_metadata_key(task_id))


def extract_task_kwargs(body) -> dict[str, Any]:
    if isinstance(body, dict):
        kwargs = body.get("kwargs")
        return kwargs if isinstance(kwargs, dict) else {}
    if isinstance(body, (list, tuple)) and len(body) >= 2 and isinstance(body[1], dict):
        return body[1]
    return {}


@before_task_publish.connect
def store_published_task_metadata(headers=None, body=None, **kwargs) -> None:
    if not isinstance(headers, dict):
        return
    headers.setdefault(CHANGE_ORIGIN_HEADER, get_change_origin())
    user = get_acting_user()
    headers.setdefault(ACTING_USER_HEADER, user.pk if user is not None else None)
    automation = headers[CHANGE_ORIGIN_HEADER].get("automation")
    if automation:
        headers["weblate_automation_origin"] = automation["activity_id"]
    elif origin := automation_origin.get():
        headers["weblate_automation_origin"] = origin
    task_kwargs = extract_task_kwargs(body)
    component_id = task_kwargs.get("component_id")
    translation_id = task_kwargs.get("translation_id")
    if component_id is None and translation_id is None:
        return
    store_task_metadata(
        headers.get("id"),
        component_id=component_id,
        translation_id=translation_id,
    )


@task_prerun.connect
def restore_automation_origin(task=None, **kwargs) -> None:
    if task is not None:
        headers = task.request.headers or {}
        origin = headers.get("weblate_automation_origin")
        if origin is None:
            # Eager and deferred tasks can carry provenance only in this header.
            change = headers.get(CHANGE_ORIGIN_HEADER) or {}
            origin = change.get("automation", {}).get(
                "activity_id", automation_origin.get()
            )
        task.request.automation_origin_token = automation_origin.set(origin)


@task_postrun.connect
def reset_automation_origin(task=None, **kwargs) -> None:
    if (
        task is not None
        and (token := getattr(task.request, "automation_origin_token", None))
        is not None
    ):
        automation_origin.reset(token)


@task_prerun.connect
def restore_change_origin(task=None, **kwargs) -> None:
    if task is not None:
        headers = task.request.headers or {}
        origin = headers.get(CHANGE_ORIGIN_HEADER)
        if origin is None:
            origin = (
                get_change_origin() if task.request.is_eager else {"scope": "system"}
            )
        task.request.change_origin_token = change_origin.set(deepcopy(origin))


@task_postrun.connect
def reset_change_origin(task=None, **kwargs) -> None:
    if (
        task is not None
        and (token := getattr(task.request, "change_origin_token", None)) is not None
    ):
        change_origin.reset(token)


@task_postrun.connect
def handle_task_failure_result(task_id=None, retval=None, **kwargs) -> None:
    """Preserve opted-in failure diagnostics before exposing a generic result."""
    if not task_id or not isinstance(retval, dict):
        return
    if retval.get("_automatic_translation_failed") is True and isinstance(
        retval.get("message"), str
    ):
        with suppress(DatabaseError, OSError):
            record_task_failure(task_id, retval["message"])
        return


@task_failure.connect
def handle_task_failure(task_id="", exception=None, **kwargs) -> None:
    if exception is not None:
        # A database outage must not prevent reporting the original failure.
        with suppress(DatabaseError, OSError):
            record_task_failure(task_id, exception)
    task_kwargs = kwargs.get("kwargs")
    if isinstance(task_kwargs, dict) and task_kwargs.get("activity_log_id") is not None:
        # ruff: ignore[import-outside-top-level]
        from weblate.addons.events import AddonActivityLogStatus

        # ruff: ignore[import-outside-top-level]
        from weblate.addons.tasks import update_addon_activity_log

        update_addon_activity_log(
            task_kwargs["activity_log_id"],
            str(exception),
            status=AddonActivityLogStatus.ERROR,
            task_count=task_kwargs.get("activity_log_task_count"),
        )

    # ruff: ignore[import-outside-top-level]
    from weblate.utils.errors import report_error, report_message

    cause = f"Failure while executing task {task_id}"
    if exception is None:
        report_message(cause, skip_error_reporting=True, level="error")
    else:
        report_error(
            cause,
            exception=exception,
            skip_error_reporting=True,
            print_tb=True,
            level="error",
        )


@app.on_after_configure.connect
def configure_error_handling(sender, **kwargs) -> None:
    """Rollbar and Sentry integration."""
    # ruff: ignore[import-outside-top-level]
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
    with app.connection_or_acquire() as conn:  # type: ignore[attr-defined]
        return conn.default_channel.queue_declare(
            queue=queue, durable=True, auto_delete=False
        ).message_count


def get_queue_list() -> set[str]:
    """List queues in Celery."""
    result = {"celery"}
    for route in settings.CELERY_TASK_ROUTES.values():
        if "queue" in route:
            result.add(route["queue"])
    return result


def get_queue_stats() -> dict[str, int]:
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


def is_celery_queue_long() -> bool:
    """
    Check whether celery queue is too long.

    It does trigger if it is too long for at least one hour. This way peaks are
    filtered out, and no warning need be issued for big operations (for example
    site-wide autotranslation).
    """
    # ruff: ignore[import-outside-top-level]
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
