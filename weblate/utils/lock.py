# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, cast

import sentry_sdk
from django.core.cache import cache
from filelock import FileLock, Timeout

from weblate.utils.cache import is_redis_cache
from weblate.utils.errors import add_breadcrumb

if TYPE_CHECKING:
    from types import TracebackType

    from django_redis.cache import RedisCache
    from redis.lock import Lock as RedisLock


class WeblateLockError(Exception):
    def __init__(self, message: str, *, lock: WeblateLock) -> None:
        super().__init__(message)
        self.lock = lock


class WeblateLockTimeoutError(WeblateLockError):
    """Weblate lock timeout."""


class WeblateLockNotLockedError(WeblateLockError):
    """Weblate lock not locked on release."""


class WeblateLock:
    """Wrapper around Redis or file based lock."""

    _redis_lock: RedisLock
    _file_lock: FileLock

    _redis_expiry_timeout = 3600

    def __init__(
        self,
        *,
        lock_path: str,
        scope: str,
        key: int | str,
        slug: str,
        cache_template: str = "lock:{scope}:{key}",
        file_template: str = "{slug}-{scope}.lock",
        timeout: int = 1,
        origin: str | None = None,
    ) -> None:
        self._timeout = timeout
        self._lock_path = lock_path
        self._scope = scope
        self._key = key
        self._slug = slug
        self._origin = origin
        self._using_redis = is_redis_cache()
        self._local = threading.local()
        self._local.depth = 0
        if self._using_redis:
            # Prefer Redis locking as it works distributed
            self._name = self._format_template(cache_template)
            self._redis_lock = cast("RedisCache", cache).lock(
                key=self._name,
                blocking=True,
                timeout=self._redis_expiry_timeout,
                blocking_timeout=self._timeout,
                thread_local=True,
            )
        else:
            # Fall back to file based locking
            self._name = os.path.join(lock_path, self._format_template(file_template))
            self._file_lock = FileLock(
                self._name,
                timeout=self._timeout,
            )

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def origin(self) -> str | None:
        return self._origin

    def _format_template(self, template: str) -> str:
        return template.format(
            scope=self._scope,
            key=self._key,
            slug=self._slug,
        )

    def get_error_message(self) -> str:
        if self.origin:
            return f"Lock on {self.origin} ({self.scope}) could not be acquired in {self._timeout}s"
        return f"Lock on {self._name} could not be acquired in {self._timeout}s"

    def _enter_redis(self) -> None:
        # Make the lock reentrant
        if self._redis_lock.owned():
            # Extend lock if already owned (nested with statements)
            lock_result = self._redis_lock.extend(
                additional_time=self._redis_expiry_timeout
            )
        else:
            lock_result = self._redis_lock.acquire()

        if not lock_result:
            raise WeblateLockTimeoutError(self.get_error_message(), lock=self)

    def _enter_file(self) -> None:
        # Fall back to file based locking
        try:
            self._file_lock.acquire()
        except Timeout as error:
            raise WeblateLockTimeoutError(
                self.get_error_message(), lock=self
            ) from error

    def add_breadcrumb(self, operation: str) -> None:
        add_breadcrumb(
            category="lock", message=f"{operation} {self._name} ({self._local.depth})"
        )

    def __enter__(self) -> None:
        self.add_breadcrumb("enter")
        if not self.is_locked:
            self.add_breadcrumb("acquire")
            with sentry_sdk.start_span(op="lock.wait", name=self._name):
                if self._using_redis:
                    self._enter_redis()
                else:
                    self._enter_file()
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

        # Release underlying lock
        if self._local.depth == 0:
            self.add_breadcrumb("release")
            if self._using_redis:
                self._redis_lock.release()
            else:
                self._file_lock.release()

    @property
    def is_locked(self) -> bool:
        return self._local.depth > 0
