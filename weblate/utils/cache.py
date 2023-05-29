# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.cache import caches
from django.utils.functional import SimpleLazyObject
from django_redis.cache import RedisCache


def is_redis_cache() -> bool:
    return isinstance(caches["default"], RedisCache)


IS_USING_REDIS = SimpleLazyObject(is_redis_cache)
