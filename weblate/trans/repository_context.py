# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING, Literal, cast

from weblate.trans.actions import ActionEvents
from weblate.utils.change_origin import change_origin_context, get_change_origin

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Any

    from weblate.utils.lock import WeblateLockTimeoutError


RepositoryOperationFollowup = Literal[
    "file-sync", "pull", "pull-skip-push", "reset-keep"
]


def repository_changes[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """Attribute parsed repository content, while preserving upload attribution."""

    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        instance = cast("Any", args[0])
        change = kwargs.get("change")
        if len(args) > 3:
            # Translation.check_sync also accepts positional change arguments.
            change = args[3]
        if change in {ActionEvents.REPLACE_UPLOAD, ActionEvents.SOURCE_UPLOAD} or (
            getattr(instance, "update_unit_change_action", None)
            == ActionEvents.STRING_UPLOAD_UPDATE
        ):
            return method(*args, **kwargs)
        if get_change_origin()["scope"] == "automation":
            return method(*args, **kwargs)
        with change_origin_context({"scope": "repository"}):
            return method(*args, **kwargs)

    return wrapped


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
