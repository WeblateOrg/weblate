# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import contextlib
from hashlib import sha256
from ipaddress import ip_address
from typing import TYPE_CHECKING

from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.throttling import UserRateThrottle as DRFUserRateThrottle

from weblate.api.ratelimits import get_rate_policies

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class RateOverrideThrottle(SimpleRateThrottle):
    """Apply Weblate settings while retaining DRF's cache and window handling."""

    override_key: str | None = None

    def get_rate(self) -> str | None:
        policies = get_rate_policies()
        return policies.anon.rate if self.scope == "anon" else policies.user.rate

    def allow_request(self, request: Request, view: APIView) -> bool:
        authenticated = bool(request.user and request.user.is_authenticated)
        if self.scope == "anon" and authenticated:
            return True

        policies = get_rate_policies()
        policy = policies.users.get(request.user.username) if authenticated else None
        address = None
        if policy is None and policies.networks:
            with contextlib.suppress(ValueError):
                address = ip_address(request.META.get("REMOTE_ADDR", ""))
            if address is not None:
                policy = next(
                    (
                        candidate
                        for network, candidate in policies.networks
                        if address in network
                    ),
                    None,
                )
        if policy is not None:
            # Anonymous overrides are enforced only by AnonRateThrottle.
            if not authenticated and self.scope == "user":
                return True
            self.rate = policy.rate
            self.num_requests = policy.num_requests
            self.duration = policy.duration
            ident = str(request.user.pk) if authenticated else str(address)
            key = f"{policy.key}:{policy.num_requests}:{policy.duration}:{ident}"
            self.override_key = (
                f"throttle_override_{self.scope}_{sha256(key.encode()).hexdigest()}"
            )
        result = super().allow_request(request, view)
        # Expose throttling state to ThrottlingMiddleware for response headers.
        if hasattr(self, "history"):
            request.META["throttling_state"] = self
        return result

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        if self.override_key is not None:
            return self.override_key
        return super().get_cache_key(request, view)


class AnonRateThrottle(RateOverrideThrottle, DRFAnonRateThrottle):
    pass


class UserRateThrottle(RateOverrideThrottle, DRFUserRateThrottle):
    pass
