# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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


def get_ip_address(request):
    """Return IP address for request."""
    if settings.IP_BEHIND_REVERSE_PROXY:
        proxy = request.META.get(settings.IP_PROXY_HEADER)
    else:
        proxy = None
    if proxy:
        # X_FORWARDED_FOR returns client1, proxy1, proxy2,...
        return proxy.split(', ')[settings.IP_PROXY_OFFSET]
    else:
        return request.META.get('REMOTE_ADDR', '')


def get_cache_key(request=None, address=None):
    """Generate cache key for request."""
    if address is None:
        address = get_ip_address(request)
    return 'ratelimit-{0}'.format(
        md5(force_bytes(address)).hexdigest()
    )


def reset_rate_limit(request=None, address=None):
    """Resets rate limit."""
    cache.delete(
        get_cache_key(request, address)
    )


def check_rate_limit(request):
    """Check authentication rate limit."""
    key = get_cache_key(request)
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
