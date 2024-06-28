# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from contextlib import suppress
from typing import cast

import sentry_sdk
from django.core.cache import cache
from django_redis.cache import RedisCache
from filelock import FileLock, Timeout
from redis_lock import AlreadyAcquired, NotAcquired

from weblate.utils.cache import is_redis_cache


class WeblateLockTimeoutError(Exception):
    """Weblate lock timeout."""


class WeblateLock:
    """Wrapper around Redis or file based lock."""

    def __init__(
        self,
        lock_path: str,
        scope: str,
        key: int,
        slug: str,
        cache_template: str = "lock:{scope}:{key}",
        file_template: str = "{slug}-{scope}.lock",
        timeout: int = 1,
    ) -> None:
        self._timeout = timeout
        self._lock_path = lock_path
        self._scope = scope
        self._key = key
        self._slug = slug
        self._depth = 0
        if is_redis_cache():
            # Prefer Redis locking as it works distributed
            self._name = self._format_template(cache_template)
            self._lock = cast(RedisCache, cache).lock(
                key=self._name,
                expire=3600,
                auto_renewal=True,
            )
            self._enter_implementation = self._enter_redis
        else:
            # Fall back to file based locking
            self._name = os.path.join(lock_path, self._format_template(file_template))
            self._lock = FileLock(self._name, timeout=self._timeout)
            self._enter_implementation = self._enter_file

    def _format_template(self, template: str):
        return template.format(
            scope=self._scope,
            key=self._key,
            slug=self._slug,
        )

    def _enter_redis(self) -> None:
        try:
            lock_result = self._lock.acquire(timeout=self._timeout)
        except AlreadyAcquired:
            return

        if not lock_result:
            raise WeblateLockTimeoutError(
                f"Lock on {self._name} could not be acquired in {self._timeout}s"
            )

    def _enter_file(self) -> None:
        # Fall back to file based locking
        try:
            self._lock.acquire()
        except Timeout as error:
            raise WeblateLockTimeoutError(str(error)) from error

    def __enter__(self):
        self._depth += 1
        if self._depth > 1:
            return
        with sentry_sdk.start_span(op="lock.wait", description=self._name):
            self._enter_implementation()

    def __exit__(self, exc_type, exc_value, traceback):
        self._depth -= 1
        if self._depth > 0:
            return
        # This can happen in case of overloaded server fails to renew the
        # lock before expiry
        with suppress(NotAcquired):
            self._lock.release()

    @property
    def is_locked(self):
        return bool(self._depth)
