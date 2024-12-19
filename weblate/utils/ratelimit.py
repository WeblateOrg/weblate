# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect
from django.template.loader import render_to_string

from weblate.logger import LOGGER
from weblate.utils import messages
from weblate.utils.cache import is_redis_cache
from weblate.utils.docs import get_doc_url
from weblate.utils.hash import calculate_checksum
from weblate.utils.request import get_ip_address

if TYPE_CHECKING:
    from django_redis.cache import RedisCache

    from weblate.auth.models import AuthenticatedHttpRequest, User


def get_cache_key(
    scope: str,
    request: AuthenticatedHttpRequest | None = None,
    address: str | None = None,
    user: User | None = None,
) -> str:
    """Generate cache key for request."""
    if request is not None and request.user.is_authenticated and user is None:
        user = request.user
    if user is not None:
        key = user.id
        origin = "user"
    else:
        if address is None:
            address = get_ip_address(request)
            if not address:
                LOGGER.error(
                    "could not obtain remote IP address, see %s",
                    get_doc_url("admin/install", "reverse-proxy"),
                )
        origin = "ip"
        key = calculate_checksum(address)
    return f"ratelimit-{origin}-{scope}-{key}"


def reset_rate_limit(
    scope, request: AuthenticatedHttpRequest | None = None, address=None, user=None
) -> None:
    """Reset rate limit."""
    cache.delete(get_cache_key(scope, request, address, user))


def get_rate_setting(scope: str, suffix: str):
    key = f"RATELIMIT_{scope.upper()}_{suffix}"
    if hasattr(settings, key):
        return getattr(settings, key)
    return getattr(settings, f"RATELIMIT_{suffix}")


def revert_rate_limit(scope, request: AuthenticatedHttpRequest) -> None:
    """
    Revert rate limit to previous state.

    This can be used when rate limiting POST, but ignoring some events.
    """
    key = get_cache_key(scope, request)

    with suppress(ValueError):
        # Try to increase bucket if it exists
        cache.incr(key)


def rate_limit(key: str, attempts: int, window: int) -> bool:
    """Verify rate limiting limits."""
    # Initialize the bucket (atomically on redis)
    if not is_redis_cache():
        if cache.get(key) is None:
            cache.set(key, attempts, window)
    else:
        cast("RedisCache", cache).set(key, attempts, window, nx=True)

    try:
        # Count current event
        cache.decr(key)
    except ValueError:
        current = 0
    else:
        # Get remaining bucket
        current = cache.get(key, 0)

    return current < 0


def check_rate_limit(scope: str, request: AuthenticatedHttpRequest) -> bool:
    """Check authentication rate limit."""
    if request.user.is_superuser:
        return True

    key = get_cache_key(scope, request)
    window = get_rate_setting(scope, "WINDOW")
    attempts = get_rate_setting(scope, "ATTEMPTS")

    if rate_limit(key, attempts, window):
        # Set key to longer expiry for lockout period
        cache.touch(key, get_rate_setting(scope, "LOCKOUT"))
        LOGGER.info(
            "rate-limit lockout for %s in %s scope from %s",
            key,
            scope,
            get_ip_address(request),
        )
        return False

    return True


def session_ratelimit_post(scope: str, logout_user: bool = True):
    def session_ratelimit_post_inner(function):
        """Session based rate limiting for POST requests."""

        def rate_wrap(request: AuthenticatedHttpRequest, *args, **kwargs):
            if request.method == "POST" and not check_rate_limit(scope, request):
                # Rotate session token
                rotate_token(request)
                if not logout_user:
                    messages.error(
                        request,
                        render_to_string(
                            "ratelimit.html", {"do_logout": False, "user": request.user}
                        ),
                    )
                    return redirect(request.get_full_path())
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
