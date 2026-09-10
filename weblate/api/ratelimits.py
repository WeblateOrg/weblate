# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class RatePolicy:
    key: str
    rate: str | None
    num_requests: int | None
    duration: int | None


def parse_rate(
    name: str, value: object, *, override: bool = False
) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    msg = f"Invalid API rate limit in {name}: {value!r}. Use a rate such as '100/hour' or None."
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+/[smhd][^/]*", value):
        raise ImproperlyConfigured(msg)
    count, period = value.split("/")
    try:
        num_requests = int(count)
    except ValueError as error:
        raise ImproperlyConfigured(msg) from error
    if override and num_requests == 0:
        raise ImproperlyConfigured(msg)
    return num_requests, {"s": 1, "m": 60, "h": 3600, "d": 86400}[period[0]]


def freeze_overrides(name: str) -> tuple[tuple[str, str | None], ...]:
    value = getattr(settings, name, {})
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str)
        or not key
        or (rate is not None and not isinstance(rate, str))
        for key, rate in value.items()
    ):
        msg = f"{name} must map nonempty strings to API rates or None."
        raise ImproperlyConfigured(msg)
    return tuple(value.items())


@dataclass(frozen=True)
class RatePolicies:
    anon: RatePolicy
    user: RatePolicy
    users: Mapping[str, RatePolicy]
    networks: tuple[tuple[IPv4Network | IPv6Network, RatePolicy], ...]


@lru_cache(maxsize=32)
def compile_policies(
    anon: str | None,
    user: str | None,
    users: tuple[tuple[str, str | None], ...],
    ips: tuple[tuple[str, str | None], ...],
) -> RatePolicies:
    user_policies = {
        name: RatePolicy(
            f"user:{name}",
            rate,
            *parse_rate("API_RATELIMIT_USER_OVERRIDES", rate, override=True),
        )
        for name, rate in users
    }
    networks: dict[IPv4Network | IPv6Network, RatePolicy] = {}
    for address, rate in ips:
        try:
            network = ip_network(address)
        except ValueError as error:
            msg = f"Invalid network in API_RATELIMIT_IP_OVERRIDES: {address!r}."
            raise ImproperlyConfigured(msg) from error
        if network in networks:
            msg = f"Duplicate network in API_RATELIMIT_IP_OVERRIDES: {address!r}."
            raise ImproperlyConfigured(msg)
        networks[network] = RatePolicy(
            f"ip:{network}",
            rate,
            *parse_rate("API_RATELIMIT_IP_OVERRIDES", rate, override=True),
        )
    return RatePolicies(
        RatePolicy("anon", anon, *parse_rate("API_RATELIMIT_ANON", anon)),
        RatePolicy("user", user, *parse_rate("API_RATELIMIT_USER", user)),
        user_policies,
        tuple(
            sorted(networks.items(), key=lambda item: item[0].prefixlen, reverse=True)
        ),
    )


def get_rate_policies() -> RatePolicies:
    anon = getattr(settings, "API_RATELIMIT_ANON", "100/day")
    user = getattr(settings, "API_RATELIMIT_USER", "5000/hour")
    # Validate before constructing the cache key, including unhashable values.
    parse_rate("API_RATELIMIT_ANON", anon)
    parse_rate("API_RATELIMIT_USER", user)
    return compile_policies(
        anon,
        user,
        freeze_overrides("API_RATELIMIT_USER_OVERRIDES"),
        freeze_overrides("API_RATELIMIT_IP_OVERRIDES"),
    )
