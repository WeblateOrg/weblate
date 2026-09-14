# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import threading
import time
from typing import TYPE_CHECKING, Protocol

from django.db import connection, transaction

from weblate.utils.errors import add_breadcrumb
from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from types import TracebackType


LOCK_SCOPE_REPOSITORY = 1
LOCK_SCOPE_COMPONENT_UPDATE = 2
LOCK_SCOPE_COMPONENT_CHECKS = 3
LOCK_SCOPE_PROJECT_CHECKS = 4
LOCK_SCOPE_STATS_UPDATE = 5
LOCK_SCOPE_VCS_SETUP = 6
LOCK_SCOPE_VCS_API_THROTTLE = 7
LOCK_SCOPE_SCREENSHOTS_TESSERACT = 8
LOCK_SCOPE_BACKUP = 9

LOCK_POLL_INTERVAL = 0.1
LOCK_DEFAULT_TIMEOUT = 1


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


class WeblateLock:
    """PostgreSQL transaction-scoped advisory lock."""

    def __init__(
        self,
        *,
        scope: str,
        key: int | str,
        slug: str,
        timeout: float = LOCK_DEFAULT_TIMEOUT,
        origin: str | None = None,
        shared: bool = False,
    ) -> None:
        self._scope = scope
        self._key = key
        self._slug = slug
        self._timeout = timeout
        self._origin = origin
        self._shared = shared
        self._local = threading.local()
        self._local.depth = 0
        self._transaction = None
        self._name = f"postgresql:{scope}:{key}"

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def origin(self) -> str | None:
        return self._origin

    @property
    def name(self) -> str:
        return self._name

    @property
    def scope_key(self) -> int:
        try:
            return {
                "repository": LOCK_SCOPE_REPOSITORY,
                "component:update": LOCK_SCOPE_COMPONENT_UPDATE,
                "component:checks": LOCK_SCOPE_COMPONENT_CHECKS,
                "project:checks": LOCK_SCOPE_PROJECT_CHECKS,
                "stats:update": LOCK_SCOPE_STATS_UPDATE,
                "vcs:setup": LOCK_SCOPE_VCS_SETUP,
                "vcs:api:throttle": LOCK_SCOPE_VCS_API_THROTTLE,
                "screenshots:tesseract:download": LOCK_SCOPE_SCREENSHOTS_TESSERACT,
                "backup:run": LOCK_SCOPE_BACKUP,
            }[self._scope]
        except KeyError as error:
            msg = f"Unknown lock scope: {self._scope}"
            raise ValueError(msg) from error

    @property
    def lock_key(self) -> int:
        """Return the 32-bit PostgreSQL advisory lock key."""
        if isinstance(self._key, int):
            key = self._key
        else:
            digest = hashlib.sha256(str(self._key).encode("utf-8")).digest()
            key = int.from_bytes(digest[:4], byteorder="big", signed=True)

        if not -(2**31) <= key < 2**31:
            msg = f"Lock key is outside PostgreSQL int4 range: {key}"
            raise ValueError(msg)

        return key

    @property
    def _try_lock_query(self) -> str:
        if self._shared:
            return "SELECT pg_try_advisory_xact_lock_shared(%s, %s)"
        return "SELECT pg_try_advisory_xact_lock(%s, %s)"

    def get_error_message(self) -> str:
        if self.origin:
            return (
                f"Lock on {self._name} ({self.origin} / {self.scope}) "
                f"could not be acquired in {self._timeout}s"
            )
        return f"Lock on {self._name} could not be acquired in {self._timeout}s"

    def add_breadcrumb(self, operation: str) -> None:
        add_breadcrumb(
            category="lock",
            message=f"{operation} {self._name} ({self._local.depth})",
        )

    def __enter__(self) -> None:
        self.add_breadcrumb("enter")

        if not self.is_locked:
            self.add_breadcrumb("acquire")
            self._transaction = None

            if not connection.in_atomic_block:
                self._transaction = transaction.atomic()
                self._transaction.__enter__()

            deadline = time.monotonic() + self._timeout

            try:
                with start_span(op="lock.wait", name=self._name):
                    while True:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                self._try_lock_query,
                                [self.scope_key, self.lock_key],
                            )
                            result = cursor.fetchone()

                        if result is not None and result[0]:
                            break

                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            self.add_breadcrumb("timeout")
                            raise WeblateLockTimeoutError(
                                self.get_error_message(),
                                lock=self,
                            )

                        time.sleep(min(LOCK_POLL_INTERVAL, remaining))
            except BaseException as exc:
                if self._transaction is not None:
                    self._transaction.__exit__(
                        type(exc),
                        exc,
                        exc.__traceback__,
                    )
                    self._transaction = None
                raise

        self._local.depth += 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self.is_locked:
            msg = f"Lock on {self._name} was not held on release"
            raise WeblateLockNotLockedError(msg, lock=self)

        self.add_breadcrumb("exit")
        self._local.depth -= 1

        if self._local.depth == 0:
            self.add_breadcrumb("release")
            transaction_context = self._transaction
            self._transaction = None

            if transaction_context is not None:
                transaction_context.__exit__(
                    exc_type,
                    exc_value,
                    traceback,
                )

    @property
    def is_locked(self) -> bool:
        return self._local.depth > 0
