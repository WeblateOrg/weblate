# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from weblate.utils.lock import WeblateLockTimeoutError


RepositoryOperationFollowup = Literal["file-sync", "pull", "reset-keep"]


class RepositoryFollowupLockError(Exception):
    """Mark lock contention after the main repository operation committed."""

    def __init__(
        self,
        error: WeblateLockTimeoutError,
        followup: RepositoryOperationFollowup,
        *,
        previous_head: str | None = None,
    ) -> None:
        super().__init__(str(error))
        self.error = error
        self.followup = followup
        self.previous_head = previous_head


repository_task_inline_followups: ContextVar[bool] = ContextVar(
    "repository_task_inline_followups", default=False
)
repository_task_suppress_auto_push: ContextVar[bool] = ContextVar(
    "repository_task_suppress_auto_push", default=False
)
repository_task_deferred_auto_push: ContextVar[dict[int, Callable[[], None]] | None] = (
    ContextVar("repository_task_deferred_auto_push", default=None)
)
repository_task_deferred_background_tasks: ContextVar[
    list[Callable[[], None]] | None
] = ContextVar("repository_task_deferred_background_tasks", default=None)
repository_task_progress_scope: ContextVar[tuple[int, int] | None] = ContextVar(
    "repository_task_progress_scope", default=None
)


@contextmanager
def inline_repository_followups() -> Generator[None]:
    token = repository_task_inline_followups.set(True)
    try:
        yield
    finally:
        repository_task_inline_followups.reset(token)


@contextmanager
def suppress_repository_auto_push() -> Generator[None]:
    token = repository_task_suppress_auto_push.set(True)
    try:
        yield
    finally:
        repository_task_suppress_auto_push.reset(token)


@contextmanager
def defer_repository_auto_push() -> Generator[dict[int, Callable[[], None]]]:
    deferred: dict[int, Callable[[], None]] = {}
    token = repository_task_deferred_auto_push.set(deferred)
    try:
        yield deferred
    finally:
        repository_task_deferred_auto_push.reset(token)


@contextmanager
def defer_repository_background_tasks() -> Generator[list[Callable[[], None]]]:
    deferred: list[Callable[[], None]] = []
    token = repository_task_deferred_background_tasks.set(deferred)
    try:
        yield deferred
    finally:
        repository_task_deferred_background_tasks.reset(token)


@contextmanager
def repository_component_progress(completed: int, total: int) -> Generator[None]:
    token = repository_task_progress_scope.set((completed, total))
    try:
        yield
    finally:
        repository_task_progress_scope.reset(token)
