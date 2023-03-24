# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from contextlib import suppress
from typing import Optional

from django.core.cache import cache
from filelock import FileLock, Timeout
from redis_lock import AlreadyAcquired, Lock, NotAcquired

from weblate.utils.cache import IS_USING_REDIS


class WeblateLockTimeout(Exception):
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
        file_template: Optional[str] = "{slug}-{scope}.lock",
        timeout: int = 1,
    ):
        self._timeout = timeout
        self._lock_path = lock_path
        self._scope = scope
        self._key = key
        self._slug = slug
        self._depth = 0
        self.use_redis = IS_USING_REDIS
        if self.use_redis:
            # Prefer Redis locking as it works distributed
            self._lock = Lock(
                cache.client.get_client(),
                name=self._format_template(cache_template),
                expire=60,
                auto_renewal=True,
            )
        else:
            # Fall back to file based locking
            self._lock = FileLock(
                os.path.join(lock_path, self._format_template(file_template)),
                timeout=self._timeout,
            )

    def _format_template(self, template: str):
        return template.format(
            scope=self._scope,
            key=self._key,
            slug=self._slug,
        )

    def __enter__(self):
        self._depth += 1
        if self._depth > 1:
            return
        if self.use_redis:
            try:
                if not self._lock.acquire(timeout=self._timeout):
                    raise WeblateLockTimeout(
                        f"Lock could not be acquired in {self._timeout}s"
                    )
            except AlreadyAcquired:
                pass
        else:
            # Fall back to file based locking
            try:
                self._lock.acquire()
            except Timeout as error:
                raise WeblateLockTimeout(str(error))

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
