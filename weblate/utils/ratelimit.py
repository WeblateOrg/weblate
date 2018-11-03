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
from time import time

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect
from django.utils.encoding import force_bytes
from django.utils.translation import ugettext as _

from weblate.utils import messages
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


def get_rate_setting(scope, suffix):
    key = 'RATELIMIT_{}_{}'.format(scope.upper(), suffix)
    if hasattr(settings, key):
        return getattr(settings, key)
    return getattr(settings, 'RATELIMIT_{}'.format(suffix))


def check_rate_limit(scope, request):
    """Check authentication rate limit."""
    key = get_cache_key(scope, request)
    attempts = cache.get(key) or 0

    if attempts >= get_rate_setting(scope, 'ATTEMPTS'):
        cache.set(key, attempts, get_rate_setting(scope, 'LOCKOUT'))
        return False

    try:
        attempts = cache.incr(key)
    except ValueError:
        # No such key, so set it
        cache.set(key, 1, get_rate_setting(scope, 'WINDOW'))

    return True


def session_ratelimit_post(scope):
    def session_ratelimit_post_inner(function):
        """Session based rate limiting for POST requests."""
        def rate_wrap(request, *args, **kwargs):
            if request.method == 'POST':
                session = request.session
                now = time()
                k_timeout = '{}_timeout'.format(scope)
                k_attempts = '{}_attempts'.format(scope)
                # Reset expired counter
                if (k_timeout in session and
                        k_attempts in session and
                        session[k_timeout] <= now):
                    session[k_attempts] = 0

                # Get current attempts
                attempts = session.get(k_attempts, 0)

                # Did we hit the limit?
                if attempts >= get_rate_setting(scope, 'ATTEMPTS'):
                    # Rotate session token
                    rotate_token(request)
                    # Logout user
                    if request.user.is_authenticated:
                        logout(request)
                    messages.error(
                        request,
                        _('Too many attempts, you have been logged out!')
                    )
                    return redirect('login')

                session[k_attempts] = attempts + 1
                if k_timeout not in session:
                    window = get_rate_setting(scope, 'WINDOW')
                    session[k_timeout] = now + window

            return function(request, *args, **kwargs)
        return rate_wrap
    return session_ratelimit_post_inner
