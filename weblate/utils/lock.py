#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
import os
from typing import Optional

from django.core.cache import caches
from django_redis.cache import RedisCache
from filelock import FileLock, Timeout
from redis_lock import AlreadyAcquired, Lock, NotAcquired


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
        default_cache = caches["default"]
        self.use_redis = isinstance(default_cache, RedisCache)
        if self.use_redis:
            # Prefer Redis locking as it works distributed
            self._lock = Lock(
                default_cache.client.get_client(),
                name=self._format_template(cache_template),
                expire=5,
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
                    raise WeblateLockTimeout()
            except AlreadyAcquired:
                pass
        else:
            # Fall back to file based locking
            try:
                self._lock.acquire()
            except Timeout:
                raise WeblateLockTimeout()

    def __exit__(self, exc_type, exc_value, traceback):
        self._depth -= 1
        if self._depth > 0:
            return
        try:
            self._lock.release()
        except NotAcquired:
            # This can happen in case of overloaded server fails to renew the
            # lock before expiry
            pass

    @property
    def is_locked(self):
        return bool(self._depth)
