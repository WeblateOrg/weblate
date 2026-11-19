# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Coordinate automatic translation without blocking worker processes."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from secrets import randbelow
from typing import TYPE_CHECKING, Any, cast

from celery import current_task
from celery.utils.time import get_exponential_backoff_interval
from django.db import connection
from psycopg.pq import TransactionStatus

from weblate.logger import LOGGER
from weblate.utils.lock import WeblateLockTimeoutError

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from weblate.trans.autotranslate import BatchAutoTranslate


class AutomaticTranslationBusyError(Exception):
    def __init__(self, translation_id: int, progress: int = 0) -> None:
        super().__init__(translation_id, progress)
        self.translation_id = translation_id
        self.progress = progress

    def __str__(self) -> str:
        return f"Automatic translation is busy: {self.translation_id}"


class AutomaticTranslationSessionLostError(AutomaticTranslationBusyError):
    def __str__(self) -> str:
        return f"Automatic translation lost its database session: {self.translation_id}"


_session: ContextVar[tuple[int, object] | None] = ContextVar(
    "automatic_translation_session", default=None
)


def ensure_translation_session() -> None:
    """Never apply provider results after losing the session owning the guard."""
    guard = _session.get()
    if guard is None:
        return
    translation_id, session = guard
    if connection.connection is not session or getattr(session, "closed", False):
        raise AutomaticTranslationSessionLostError(translation_id)


@contextmanager
def translation_guard(translation_id: int) -> Generator[None]:
    key = f"weblate-autotranslate:{translation_id}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", [key])
        if not cursor.fetchone()[0]:
            raise AutomaticTranslationBusyError(translation_id)
    session = connection.connection
    token = _session.set((translation_id, session))
    try:
        if connection.in_atomic_block:
            # The session guard covers provider calls. The transaction guard
            # additionally protects writes until a surrounding edit commits.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key]
                )
        yield
        ensure_translation_session()
    finally:
        _session.reset(token)
        if connection.connection is session:
            if (
                session.closed
                or connection.needs_rollback
                or session.info.transaction_status == TransactionStatus.INERROR
            ):
                # An aborted transaction cannot execute an unlock statement.
                # Closing also prevents a broken session leaking into the pool.
                connection.close()
            else:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", [key]
                    )


class TranslationContinuation:
    def __init__(self, payload: dict[str, Any], *, defer: bool) -> None:
        self.payload = payload
        self.defer = defer
        self.completed: set[int] = set(payload.get("completed", []))
        self.task_meta: dict[str, Any] = {}

    def restore(self, auto: BatchAutoTranslate) -> None:
        targets = set(
            self.payload.setdefault("targets", [item.pk for item in auto.translations])
        )
        available = {item.pk for item in auto.translations}
        self.completed.update(set(targets) - available)
        auto.translations = [
            item
            for item in auto.translations
            if item.pk in targets and item.pk not in self.completed
        ]
        auto.progress_steps = len(targets)
        self.task_meta = auto.get_task_meta()
        auto.updated = self.payload.get("updated", 0)
        auto.failure_message = self.payload.get("failure_message")
        auto.errors = list(self.payload.get("errors", []))
        auto.error_details = list(self.payload.get("error_details", []))
        for detail in self.payload.get("warnings", []):
            auto.add_warning(
                detail["message"],
                public_message=detail["public_message"],
                component_ids=detail["component_ids"],
            )

    def checkpoint(self, auto: BatchAutoTranslate, translation_id: int) -> None:
        self.completed.add(translation_id)
        self.payload.update(
            completed=sorted(self.completed),
            updated=auto.updated,
            failure_message=auto.failure_message,
            errors=auto.get_errors(),
            error_details=auto.get_error_details(),
            warnings=auto.get_warning_details(),
        )


translation_continuation: ContextVar[TranslationContinuation | None] = ContextVar(
    "translation_continuation", default=None
)


def translation_task[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Carry partial results across busy retries without exhausting error retries."""

    @wraps(func)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        payload = cast("dict[str, Any]", kwargs.pop("_translation_resume", {}))
        failures = cast("int", kwargs.pop("_translation_failures", 0))
        defer = bool(
            current_task
            and current_task.name == f"{func.__module__}.{func.__name__}"
            and current_task.request.id
            and not current_task.request.is_eager
        )
        state = TranslationContinuation(payload, defer=defer)
        token = translation_continuation.set(state)
        try:
            if payload:
                LOGGER.info(
                    "Resuming automatic translation task %s", current_task.request.id
                )
            try:
                return func(*args, **kwargs)
            except (AutomaticTranslationBusyError, WeblateLockTimeoutError) as error:
                if not defer:
                    raise
                if isinstance(error, AutomaticTranslationBusyError):
                    targets = state.payload.get("targets", [])
                    error = type(error)(
                        error.translation_id,
                        100 * len(state.completed) // len(targets) if targets else 0,
                    )
                    countdown = 30 + randbelow(31)
                    LOGGER.info(
                        "Deferring automatic translation task %s for translation %s",
                        current_task.request.id,
                        error.translation_id,
                    )
                else:
                    if failures >= 3:
                        raise
                    countdown = get_exponential_backoff_interval(
                        factor=600, retries=failures, maximum=3600, full_jitter=True
                    )
                    failures += 1
                retry_kwargs = dict(kwargs)
                retry_kwargs.update(
                    _translation_resume=state.payload, _translation_failures=failures
                )
                raise current_task.retry(
                    args=args,
                    kwargs=retry_kwargs,
                    exc=error,
                    countdown=countdown,
                    max_retries=None,
                ) from error
        finally:
            translation_continuation.reset(token)

    return run
