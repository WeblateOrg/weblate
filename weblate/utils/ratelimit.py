# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from hashlib import md5

from django.conf import settings
from django.core.cache import cache
from django.utils.encoding import force_bytes

from weblate.utils.request import get_ip_address


def get_cache_key(scope, request=None, address=None):
    """Generate cache key for request."""
    if address is None:
        address = get_ip_address(request)
    return 'ratelimit-{0}-{1}'.format(
        scope,
        md5(force_bytes(address)).hexdigest()
    )


def reset_rate_limit(scope, request=None, address=None):
    """Resets rate limit."""
    cache.delete(
        get_cache_key(scope, request, address)
    )


def check_rate_limit(scope, request):
    """Check authentication rate limit."""
    key = get_cache_key(scope, request)
    attempts = cache.get(key) or 0

    if attempts >= settings.AUTH_MAX_ATTEMPTS:
        cache.set(key, attempts, settings.AUTH_LOCKOUT_TIME)
        return False

    try:
        attempts = cache.incr(key)
    except ValueError:
        # No such key, so set it
        cache.set(key, 1, settings.AUTH_CHECK_WINDOW)

    return True
