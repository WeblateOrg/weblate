# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from functools import wraps
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect
from django.template.loader import render_to_string
from siphashc import siphash

from weblate.logger import LOGGER
from weblate.utils import messages
from weblate.utils.docs import get_doc_url
from weblate.utils.hash import calculate_checksum
from weblate.utils.request import get_ip_address

if TYPE_CHECKING:
    from django.http import HttpResponse

    from weblate.auth.models import AuthenticatedHttpRequest, User


def get_rate_setting(scope: str, suffix: str):
    key = f"RATELIMIT_{scope.upper()}_{suffix}"
    if hasattr(settings, key):
        return getattr(settings, key)
    return getattr(settings, f"RATELIMIT_{suffix}")


def reset_rate_limit(
    scope, request: AuthenticatedHttpRequest | None = None, address=None, user=None
) -> None:
    """Reset rate limit."""
    limiter = RateLimitHttpRequest(scope, request, address, user)
    limiter.reset()


def revert_rate_limit(scope, request: AuthenticatedHttpRequest) -> None:
    """
    Revert rate limit to previous state.

    This can be used when rate limiting POST, but ignoring some events.
    """
    limiter = RateLimitHttpRequest(scope, request)
    limiter.revert()


def check_rate_limit(scope: str, request: AuthenticatedHttpRequest) -> bool:
    """Check authentication rate limit."""
    if request.user.is_superuser:
        return True

    limiter = RateLimitHttpRequest(scope, request)
    is_exceeded, _ = limiter.is_limit_exceeded()

    if is_exceeded:
        # Set key to longer expiry for lockout period
        limiter.touch(get_rate_setting(scope, "LOCKOUT"))
        LOGGER.info(
            "rate-limit lockout for %s in %s scope from %s",
            limiter.key,
            scope,
            get_ip_address(request),
        )
        return False

    return True


def session_ratelimit_post(scope: str, logout_user: bool = True):
    """Session based rate limiting for POST requests."""

    def _session_ratelimit_post_controller(function):
        def _rate_wrap(
            request: AuthenticatedHttpRequest, *args, **kwargs
        ) -> HttpResponse:
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

        return wraps(function)(_rate_wrap)

    return _session_ratelimit_post_controller


def rate_limit_notify(address: str) -> tuple[bool, str]:
    """
    Multi-level rate limiting for email notifications.

    Returns: tuple: (is_blocked, reason)
    """
    rate_limits = getattr(settings, "RATELIMIT_NOTIFICATION_LIMITS", [(1000, 86400)])
    encoded_email = siphash("Weblate notifier", address)
    limiter = RateLimitNotify(f"{encoded_email}", rate_limits)
    return limiter.is_limit_exceeded()


class RateLimitBase:
    cache_items: list[CacheCounterItem]
    key: str

    def __init__(self, base_key: str, rate_limits: list[tuple[int, int]]):
        self.key = base_key

        self.cache_items = [
            CacheCounterItem(self.key, attempts, window)
            for attempts, window in rate_limits
        ]

    def is_limit_exceeded(self) -> tuple[bool, str]:
        # Check all without decrementing
        for cache_item in self.cache_items:
            if cache_item.count_remaining <= 0:
                return (
                    True,
                    f"rate limit exceeded ({cache_item.attempts}/{cache_item.window}s)",
                )
        # If we get here, we can allow the operation - so decrement all counters
        for cache_item in self.cache_items:
            cache_item.decrement()
        return False, ""

    def touch(self, timeout: int):
        for cache_item in self.cache_items:
            cache_item.touch(timeout)

    def revert(self):
        for cache_item in self.cache_items:
            cache_item.increment()

    def reset(self):
        for cache_item in self.cache_items:
            cache_item.delete()


class RateLimitNotify(RateLimitBase):
    def __init__(self, base_key: str, rate_limits: list[tuple[int, int]]):
        RateLimitBase.__init__(self, f"notify:rate:{base_key}", rate_limits)


class RateLimitHttpRequest(RateLimitBase):
    def __init__(
        self,
        scope: str,
        request: AuthenticatedHttpRequest | None = None,
        address: str | None = None,
        user: User | None = None,
    ):
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

        base_key = f"ratelimit-{origin}-{scope}-{key}"
        window = get_rate_setting(scope, "WINDOW")
        attempts = get_rate_setting(scope, "ATTEMPTS")

        RateLimitBase.__init__(self, base_key, [(attempts, window)])


class CacheCounterItem:
    cache_key: str
    attempts: int
    window: int

    def __init__(self, base_key: str, attempts: int, window: int):
        self.cache_key = f"{base_key}:{attempts}:{window}"
        self.attempts = attempts
        self.window = window
        cache.add(self.cache_key, attempts, window)

    @property
    def count_remaining(self) -> int:
        return cache.get(self.cache_key, 0)

    def increment(self) -> None:
        with suppress(ValueError):
            cache.incr(self.cache_key)

    def decrement(self) -> None:
        with suppress(ValueError):
            cache.decr(self.cache_key)

    def touch(self, timeout: int) -> None:
        cache.touch(self.cache_key, timeout)

    def delete(self) -> None:
        cache.delete(self.cache_key)
