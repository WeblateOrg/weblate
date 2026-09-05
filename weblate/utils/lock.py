# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import threading
from typing import TYPE_CHECKING, Protocol

from django.db import connection, transaction

from weblate.utils.errors import add_breadcrumb
from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from types import TracebackType


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
        origin: str | None = None,
    ) -> None:
        self._scope = scope
        self._key = key
        self._slug = slug
        self._origin = origin
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
    def lock_key(self) -> int:
        """Return a stable signed 64-bit PostgreSQL advisory lock key."""
        digest = hashlib.sha256(f"{self._scope}:{self._key}".encode()).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    def get_error_message(self) -> str:
        if self.origin:
            return f"Lock on {self._name} ({self.origin} / {self.scope})"
        return f"Lock on {self._name}"

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

            try:
                with start_span(op="lock.wait", name=self._name):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_xact_lock(%s)",
                            [self.lock_key],
                        )
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
