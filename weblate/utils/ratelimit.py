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

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect
from django.template.loader import render_to_string

from weblate.utils import messages
from weblate.utils.hash import calculate_checksum
from weblate.utils.request import get_ip_address


def get_cache_key(scope, request=None, address=None, user=None):
    """Generate cache key for request."""
    if (request and request.user.is_authenticated) or user:
        if user:
            key = user.id
        else:
            key = request.user.id
        origin = "user"
    else:
        if address is None:
            address = get_ip_address(request)
        origin = "ip"
        key = calculate_checksum(address)
    return f"ratelimit-{origin}-{scope}-{key}"


def reset_rate_limit(scope, request=None, address=None, user=None):
    """Resets rate limit."""
    cache.delete(get_cache_key(scope, request, address, user))


def get_rate_setting(scope, suffix):
    key = f"RATELIMIT_{scope.upper()}_{suffix}"
    if hasattr(settings, key):
        return getattr(settings, key)
    return getattr(settings, f"RATELIMIT_{suffix}")


def revert_rate_limit(scope, request):
    """Revert rate limit to previous state.

    This can be used when rate limiting POST, but ignoring some events.
    """
    key = get_cache_key(scope, request)

    try:
        # Try to decrease cache key
        cache.decr(key)
    except ValueError:
        pass


def check_rate_limit(scope, request):
    """Check authentication rate limit."""
    if request.user.is_superuser:
        return True

    key = get_cache_key(scope, request)

    try:
        # Try to increase cache key
        attempts = cache.incr(key)
    except ValueError:
        # No such key, so set it
        cache.set(key, 1, get_rate_setting(scope, "WINDOW"))
        attempts = 1

    if attempts > get_rate_setting(scope, "ATTEMPTS"):
        # Set key to longer expiry for lockout period
        cache.set(key, attempts, get_rate_setting(scope, "LOCKOUT"))
        return False

    return True


def session_ratelimit_post(scope):
    def session_ratelimit_post_inner(function):
        """Session based rate limiting for POST requests."""

        def rate_wrap(request, *args, **kwargs):
            if request.method == "POST" and not check_rate_limit(scope, request):
                # Rotate session token
                rotate_token(request)
                # Logout user
                do_logout = request.user.is_authenticated
                if do_logout:
                    logout(request)
                messages.error(
                    request,
                    render_to_string(
                        "ratelimit.html", {"do_logout": do_logout, "user": request.user}
                    ),
                )
                return redirect("login")
            return function(request, *args, **kwargs)

        return rate_wrap

    return session_ratelimit_post_inner
