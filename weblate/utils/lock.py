# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import threading
from time import monotonic, sleep
from typing import TYPE_CHECKING, Protocol

from django.db import DEFAULT_DB_ALIAS, connections
from django.db.models import IntegerChoices
from psycopg.pq import TransactionStatus

from weblate.utils.errors import add_breadcrumb
from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from types import TracebackType


class LockScope(IntegerChoices):
    """Stable PostgreSQL namespaces. Values must never be reassigned."""

    REPOSITORY = 1, "repository"
    COMPONENT_UPDATE = 2, "component:update"
    COMPONENT_CHECKS = 3, "component:checks"
    PROJECT_CHECKS = 4, "project:checks"
    WORKSPACE_CHECKS = 5, "workspace:checks"
    STATS_UPDATE = 6, "stats:update"
    VCS_SETUP = 7, "vcs:setup"
    VCS_API_THROTTLE = 8, "vcs:api:throttle"
    SCREENSHOTS_TESSERACT_DOWNLOAD = 9, "screenshots:tesseract:download"
    MACHINERY_REQUEST = 10, "machinery-request"
    AI_EVALUATION = 11, "ai-evaluation"
    KOTLIN_SDK = 12, "kotlin-sdk"
    BROWSER_UPLOAD = 13, "browser-upload"
    TASK_METADATA = 14, "task-metadata"
    SECURITY_CONFIRM = 15, "security-confirm"
    NOTIFY_RESERVATION = 16, "notify-reservation"
    CONTRIBUTOR_METRICS = 17, "contributor-metrics"


class LockInfo(Protocol):
    """Lock metadata exposed on lock errors."""

    @property
    def name(self) -> str: ...

    @property
    def scope(self) -> str: ...

    @property
    def origin(self) -> str | None: ...


class WeblateLockError(Exception):
    def __init__(self, message: str, *, lock: LockInfo) -> None:
        super().__init__(message)
        self.lock = lock


class WeblateLockTimeoutError(WeblateLockError):
    """Weblate lock timeout."""


class WeblateLockNotLockedError(WeblateLockError):
    """Weblate lock not locked on release."""


class AdvisoryLock:
    """A PostgreSQL lock with either a lexical or transaction lifetime."""

    def __init__(
        self,
        key: int | str | tuple[int, int],
        *,
        scope: str,
        shared: bool = False,
        timeout: float | None = None,
        origin: str | None = None,
        using: str = DEFAULT_DB_ALIAS,
    ) -> None:
        self.scope = scope
        self.origin = origin
        self.name = f"postgresql:{scope}:{key}"
        self._using = using
        self._timeout = timeout
        self._shared = shared
        self._local = threading.local()
        self._key = key
        self._params: list[int] | list[str]
        if isinstance(key, tuple):
            self._arguments = "%s, %s"
            self._params = list(key)
        elif isinstance(key, str):
            # Existing check and translation guards use PostgreSQL's text hash.
            self._arguments = "hashtextextended(%s, 0)"
            self._params = [key]
        else:
            self._arguments = "%s"
            self._params = [key]

    def shared_reader(self) -> AdvisoryLock:
        return AdvisoryLock(
            self._key,
            scope=self.scope,
            origin=self.origin,
            using=self._using,
            timeout=self._timeout,
            shared=True,
        )

    def _execute(self, operation: str) -> bool:
        suffix = "_shared" if self._shared else ""
        with connections[self._using].cursor() as cursor:
            cursor.execute(
                f"SELECT pg_{operation}{suffix}({self._arguments})", self._params
            )
            return bool(cursor.fetchone()[0])

    def _acquire(self, operation: str) -> None:
        with start_span(op="lock.wait", name=self.name):
            if self._timeout is None:
                self._execute(operation)
            else:
                deadline = monotonic() + self._timeout
                while not self._execute(f"try_{operation}"):
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        message = f"Lock on {self.name} could not be acquired in {self._timeout}s"
                        raise WeblateLockTimeoutError(message, lock=self)
                    sleep(min(0.1, remaining))
        add_breadcrumb(category="lock", message=f"acquire {self.name}")

    def acquire_transaction(self) -> None:
        if not connections[self._using].in_atomic_block:
            msg = "Transaction advisory locks require a database transaction"
            raise RuntimeError(msg)
        self._acquire("advisory_xact_lock")

    def ensure_session(self) -> None:
        session = self._local.session
        if session is not connections[self._using].connection or session.closed:
            msg = f"Lost session holding {self.name}"
            raise WeblateLockNotLockedError(msg, lock=self)

    @property
    def is_locked(self) -> bool:
        if getattr(self._local, "depth", 0) == 0:
            return False
        self.ensure_session()
        return True

    def __enter__(self) -> None:
        if self.is_locked:
            self._local.depth += 1
            return
        self._acquire("advisory_lock")
        self._local.session = connections[self._using].connection
        self._local.depth = 1

    def _unlock(self) -> None:
        database = connections[self._using]
        session = self._local.session
        self.ensure_session()
        if (
            database.needs_rollback
            or session.info.transaction_status == TransactionStatus.INERROR
        ):
            msg = f"Failed transaction while holding {self.name}"
            raise WeblateLockError(msg, lock=self)
        if not self._execute("advisory_unlock"):
            msg = f"Session no longer holds {self.name}"
            raise WeblateLockNotLockedError(msg, lock=self)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if getattr(self._local, "depth", 0) == 0:
            msg = f"Lock on {self.name} was not held on release"
            raise WeblateLockNotLockedError(msg, lock=self)
        self._local.depth -= 1
        if self._local.depth:
            return
        database = connections[self._using]
        session = self._local.session
        try:
            self._unlock()
        except BaseException:
            if database.connection is session:
                # Discard the physical session even when Django uses a pool.
                session.close()
                database.close()
            if exc_value is None:
                raise
        finally:
            del self._local.session
            add_breadcrumb(category="lock", message=f"release {self.name}")


class WeblateLock(AdvisoryLock):
    def __init__(
        self,
        *,
        scope: LockScope,
        key: int | str,
        timeout: float = 1,
        origin: str | None = None,
        shared: bool = False,
    ) -> None:
        identity: int | tuple[int, int]
        if isinstance(key, int) and -(2**31) <= key < 2**31:
            identity = (scope.value, key)
        else:
            digest = hashlib.blake2b(f"{scope.value}:{key}".encode(), digest_size=8)
            identity = int.from_bytes(digest.digest(), signed=True)
        super().__init__(
            identity, scope=scope.label, timeout=timeout, origin=origin, shared=shared
        )
