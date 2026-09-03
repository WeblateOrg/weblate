# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event, Thread
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from celery import uuid
from django.conf import settings
from django.core.cache import cache

from weblate.utils.celery import (
    TASK_METADATA_TTL,
    delete_task_metadata,
    get_task_metadata,
    get_task_metadata_key,
    store_task_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable

    from weblate.auth.models import User
    from weblate.trans.models import Component, Project, Translation


RepositoryOperation = Literal[
    "commit",
    "pull",
    "pull-rebase",
    "pull-merge",
    "pull-merge-noff",
    "push",
    "reset",
    "reset-keep",
    "cleanup",
    "file-sync",
    "file-scan",
    "remove-duplicates",
    "cleanup-unused",
    "remove-obsolete",
]


class RepositoryOperationReservation(TypedDict):
    operation: RepositoryOperation
    task_id: str


@dataclass(frozen=True, slots=True)
class QueuedRepositoryOperation:
    task_id: str
    reused: bool = False
    successful: bool | None = None


class RepositoryOperationConflictError(Exception):
    def __init__(self, task_id: str | None = None) -> None:
        super().__init__("A repository operation is already in progress")
        self.task_id = task_id


REPOSITORY_OPERATION_TTL = TASK_METADATA_TTL
REPOSITORY_OPERATION_HEARTBEAT = REPOSITORY_OPERATION_TTL // 3


def get_repository_operation_key(component_id: int) -> str:
    return f"repository-operation-{component_id}"


def get_repository_operation_scope_key(task_id: str) -> str:
    return f"repository-operation-scope-{task_id}"


def get_repository_operation_published_key(task_id: str) -> str:
    return f"repository-operation-published-{task_id}"


def get_repository_operation_update_key(component_id: int) -> str:
    return f"component-repository-operation-{component_id}"


def get_repository_components(
    obj: Project | Component | Translation,
    repository_components: Iterable[Component] | None = None,
) -> tuple[list[Component], list[Component]]:
    # Importing models here avoids a models -> tasks -> repository import cycle.
    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Component,
        Translation,
    )

    if repository_components is None:
        display_components = list(obj.all_repo_components)
        if isinstance(obj, Component):
            display_components.append(obj)
        elif isinstance(obj, Translation):
            display_components.append(obj.component)
    else:
        display_components = list(repository_components)

    display_by_id = {component.pk: component for component in display_components}
    repository_by_id = {
        component.effective_repo_component.pk: component.effective_repo_component
        for component in display_components
    }
    return (
        [repository_by_id[pk] for pk in sorted(repository_by_id)],
        [display_by_id[pk] for pk in sorted(display_by_id)],
    )


def get_affected_component_ids(repository_ids: list[int]) -> list[int]:
    from django.db.models import Q  # ruff: ignore[import-outside-top-level]

    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    return list(
        Component.objects.filter(
            Q(pk__in=repository_ids) | Q(linked_component_id__in=repository_ids)
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _get_active_reservation(component_id: int) -> RepositoryOperationReservation | None:
    key = get_repository_operation_key(component_id)
    reservation = cache.get(key)
    if not isinstance(reservation, dict):
        return None
    task_id = reservation.get("task_id")
    operation = reservation.get("operation")
    if not isinstance(task_id, str) or not isinstance(operation, str):
        cache.delete(key)
        return None
    return cast("RepositoryOperationReservation", reservation)


def get_repository_operation_scope(task_id: str) -> list[int] | None:
    component_ids = cache.get(get_repository_operation_scope_key(task_id))
    if not isinstance(component_ids, list) or not all(
        isinstance(component_id, int) for component_id in component_ids
    ):
        return None
    return component_ids


def acquire_repository_operation(
    component_ids: list[int], operation: RepositoryOperation, task_id: str
) -> None:
    """Acquire all repository reservations, rolling back partial acquisition."""
    reservation: RepositoryOperationReservation = {
        "operation": operation,
        "task_id": task_id,
    }
    for component_id in component_ids:
        active = _get_active_reservation(component_id)
        if active is None and cache.add(
            get_repository_operation_key(component_id),
            reservation,
            REPOSITORY_OPERATION_TTL,
        ):
            continue
        if active is None:
            active = _get_active_reservation(component_id)
        if active == reservation:
            cache.touch(
                get_repository_operation_key(component_id),
                REPOSITORY_OPERATION_TTL,
            )
            continue

        # Retries can already own later reservations in the scope. Release
        # every reservation still owned by this task, not just those visited.
        release_repository_operation(component_ids, task_id)
        raise RepositoryOperationConflictError(
            active["task_id"] if active is not None else None
        )

    cache.set(
        get_repository_operation_scope_key(task_id),
        component_ids,
        REPOSITORY_OPERATION_TTL,
    )


def release_repository_operation(component_ids: list[int], task_id: str) -> None:
    for component_id in component_ids:
        key = get_repository_operation_key(component_id)
        reservation = cache.get(key)
        if isinstance(reservation, dict) and reservation.get("task_id") == task_id:
            cache.delete(key)
    cache.delete(get_repository_operation_scope_key(task_id))
    cache.delete(get_repository_operation_published_key(task_id))


def refresh_repository_operation(
    component_ids: list[int],
    task_id: str,
    tracking_component_ids: list[int] | None = None,
) -> None:
    for component_id in component_ids:
        key = get_repository_operation_key(component_id)
        reservation = cache.get(key)
        if isinstance(reservation, dict) and reservation.get("task_id") == task_id:
            cache.touch(key, REPOSITORY_OPERATION_TTL)
    cache.touch(get_repository_operation_scope_key(task_id), REPOSITORY_OPERATION_TTL)
    cache.touch(
        get_repository_operation_published_key(task_id), REPOSITORY_OPERATION_TTL
    )
    cache.touch(get_task_metadata_key(task_id), TASK_METADATA_TTL)
    for component_id in tracking_component_ids or ():
        key = get_repository_operation_update_key(component_id)
        if cache.get(key) == task_id:
            cache.touch(key, REPOSITORY_OPERATION_TTL)


def mark_repository_operation_published(component_ids: list[int], task_id: str) -> None:
    """Mark a task reusable once all its repositories have been published."""
    if all(
        (active := _get_active_reservation(component_id)) is not None
        and active["task_id"] == task_id
        for component_id in component_ids
    ):
        cache.set(
            get_repository_operation_published_key(task_id),
            True,
            REPOSITORY_OPERATION_TTL,
        )


def store_repository_operation_tracking(
    task_id: str,
    tracking_component_ids: list[int],
    user_id: int,
    *,
    authorization_component_ids: list[int] | None = None,
) -> None:
    cache.set_many(
        {
            get_repository_operation_update_key(component_id): task_id
            for component_id in tracking_component_ids
        },
        REPOSITORY_OPERATION_TTL,
    )
    store_task_metadata(
        task_id,
        component_ids=authorization_component_ids,
        user_id=user_id,
        task_kind="repository-operation",
        cancellable=False,
    )


@contextmanager
def keep_repository_operation_reservation(
    component_ids: list[int],
    task_id: str,
    tracking_component_ids: list[int] | None = None,
) -> Generator[None]:
    """Refresh a reservation while a potentially long operation is running."""
    stopped = Event()

    def heartbeat() -> None:
        while not stopped.wait(REPOSITORY_OPERATION_HEARTBEAT):
            refresh_repository_operation(component_ids, task_id, tracking_component_ids)

    refresh_repository_operation(component_ids, task_id, tracking_component_ids)
    thread = Thread(
        target=heartbeat,
        name=f"repository-operation-{task_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=5)


@contextmanager
def reserve_repository_operation(
    component_ids: list[int], operation: RepositoryOperation
) -> Generator[Callable[[], None]]:
    """Reserve repositories and yield an idempotent early-release callback."""
    task_id = uuid()
    acquire_repository_operation(component_ids, operation, task_id)

    def release() -> None:
        release_repository_operation(component_ids, task_id)

    try:
        with keep_repository_operation_reservation(component_ids, task_id):
            yield release
    finally:
        release()


def can_access_repository_operation_task(user: User, task_id: str) -> bool:
    """Return whether a repository task URL is usable by a user."""
    metadata = get_task_metadata(task_id)
    if metadata is None:
        return False
    component_ids = metadata.get("component_ids")
    if not isinstance(component_ids, list) or not all(
        isinstance(component_id, int) for component_id in component_ids
    ):
        return False

    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    unique_component_ids = set(component_ids)
    existing_component_ids = set(
        Component.objects.filter(pk__in=unique_component_ids).values_list(
            "pk", flat=True
        )
    )
    accessible_component_ids = set(
        Component.objects.filter_access(user)
        .filter(pk__in=existing_component_ids)
        .values_list("pk", flat=True)
    )
    if accessible_component_ids != existing_component_ids:
        return False
    return (
        bool(existing_component_ids) and existing_component_ids == unique_component_ids
    ) or metadata.get("user_id") == user.pk


def get_repository_operation_tracking_ids(
    repositories: list[Component], display_components: list[Component], user: User
) -> list[int]:
    """Return components where the user can access operation progress."""
    from weblate.trans.models import Component  # ruff: ignore[import-outside-top-level]

    repository_ids = [component.pk for component in repositories]
    affected_ids = get_affected_component_ids(repository_ids)
    candidate_ids = (
        {component.pk for component in display_components}
        | set(repository_ids)
        | set(affected_ids)
    )
    return list(
        Component.objects.filter_access(user)
        .filter(pk__in=candidate_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def queue_repository_operation(
    obj: Project | Component | Translation,
    operation: RepositoryOperation,
    user: User,
    *,
    repository_components: Iterable[Component] | None = None,
) -> QueuedRepositoryOperation:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.tasks import (
        perform_repository_operation,
    )

    repositories, display_components = get_repository_components(
        obj, repository_components
    )
    repository_ids = [component.pk for component in repositories]
    existing = [
        active_reservation
        for component_id in repository_ids
        if (active_reservation := _get_active_reservation(component_id)) is not None
    ]
    if existing:
        task_ids = {reservation["task_id"] for reservation in existing}
        operations = {reservation["operation"] for reservation in existing}
        existing_task_id = next(iter(task_ids), None)
        if (
            len(existing) == len(repository_ids)
            and len(task_ids) == 1
            and operations == {operation}
            and existing_task_id is not None
            and get_repository_operation_scope(existing_task_id) == repository_ids
            and cache.get(get_repository_operation_published_key(existing_task_id))
            is True
        ):
            return QueuedRepositoryOperation(existing_task_id, reused=True)
        raise RepositoryOperationConflictError(existing_task_id)

    task_id = uuid()
    acquire_repository_operation(repository_ids, operation, task_id)
    display_ids: list[int] = []
    try:
        display_ids = get_repository_operation_tracking_ids(
            repositories, display_components, user
        )
        store_repository_operation_tracking(
            task_id,
            display_ids,
            user.pk,
            authorization_component_ids=display_ids,
        )
        task = perform_repository_operation.apply_async(
            kwargs={
                "operation": operation,
                "component_ids": repository_ids,
                "tracking_component_ids": display_ids,
                "user_id": user.pk,
            },
            task_id=task_id,
        )
        mark_repository_operation_published(repository_ids, task_id)
    except Exception:
        release_repository_operation(repository_ids, task_id)
        cache.delete_many(
            [
                get_repository_operation_update_key(component_id)
                for component_id in display_ids
            ]
        )
        delete_task_metadata(task_id)
        raise
    successful = None
    if settings.CELERY_TASK_ALWAYS_EAGER and isinstance(task.result, dict):
        result = task.result.get("result")
        if isinstance(result, bool):
            successful = result
    return QueuedRepositoryOperation(task_id, successful=successful)


def get_operation_call(
    operation: RepositoryOperation,
) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
    if operation == "commit":
        return "commit_pending", ("commit",), {}
    if operation == "pull":
        return "do_update", (), {}
    if operation == "pull-rebase":
        return "do_update", (), {"method": "rebase"}
    if operation == "pull-merge":
        return "do_update", (), {"method": "merge"}
    if operation == "pull-merge-noff":
        return "do_update", (), {"method": "merge_noff"}
    if operation == "push":
        return "do_push", (), {}
    if operation == "reset":
        return "do_reset", (), {}
    if operation == "reset-keep":
        return "do_reset", (), {"keep_changes": True}
    if operation == "cleanup":
        return "do_cleanup", (), {}
    if operation == "file-sync":
        return "do_file_sync", (), {}
    if operation == "file-scan":
        return "do_file_scan", (), {}
    raise ValueError(operation)


def get_repository_operation_permission(operation: RepositoryOperation) -> str:
    if operation == "commit":
        return "vcs.commit"
    if operation == "push":
        return "vcs.push"
    if operation.startswith("pull"):
        return "vcs.update"
    return "vcs.reset"
