# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time

from django.core.cache import cache, caches
from django_redis.cache import RedisCache


def is_redis_cache() -> bool:
    return isinstance(caches["default"], RedisCache)


def measure_cache_latency() -> float:
    start = time.monotonic()
    cache.get("celery_loaded")
    return round(1000 * (time.monotonic() - start))
