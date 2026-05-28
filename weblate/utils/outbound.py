# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.http.request import validate_host
from django.utils.translation import gettext

LOCAL_HOST_SUFFIXES = (
    ".local",
    ".localhost",
)

# IPv6 transition prefixes whose addresses encode an IPv4 destination.  On
# hosts where 6to4 / NAT64 translation is configured, the kernel routes
# packets sent to these addresses to the embedded IPv4 endpoint, so they
# must be unwrapped before consulting ipaddress.is_global - which classifies
# 2002::/16 and 64:ff9b::/96 as globally routable.
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_LOCAL_USE_PREFIX = ipaddress.IPv6Network("64:ff9b:1::/48")
_IPV4_COMPAT = ipaddress.IPv6Network("::0.0.0.0/96")


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _normalize_hostname(value: str) -> str:
    normalized = value.rstrip(".")
    if not normalized:
        return ""

    if "://" not in normalized:
        normalized = f"//{normalized}"

    hostname = urlparse(normalized).hostname
    if hostname is None:
        return value.rstrip(".")
    return hostname.rstrip(".")


def _parse_hostname_ip(
    value: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    normalized = _normalize_hostname(value)

    if ip_address := _parse_ip(normalized):
        return ip_address

    try:
        packed = socket.inet_aton(normalized)
    except OSError:
        return None

    return ipaddress.IPv4Address(packed)


def _unwrap_ipv6_transition(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """
    Return the embedded IPv4 destination for an IPv6 transition address.

    Covers IPv4-mapped IPv6 (``::ffff:0:0/96``), IPv4-compatible IPv6
    (``::0.0.0.0/96``, deprecated by RFC 4291 but still routable on hosts
    that have not removed the configuration), 6to4 (``2002::/16``,
    RFC 3056) and the well-known NAT64 prefix (``64:ff9b::/96`` per
    RFC 6052).  Returns the input unchanged when the address does not embed
    an IPv4 destination.

    Without this unwrap, ``ipaddress.IPv6Address.is_global`` classifies
    ``2002::/16`` and ``64:ff9b::/96`` as globally routable and the
    outbound-URL guard misses these forms when an attacker supplies a
    hostname whose AAAA record points at a wrapped private IPv4.
    """
    if not isinstance(address, ipaddress.IPv6Address):
        return address
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address in _NAT64_PREFIX:
        return ipaddress.IPv4Address(address.packed[-4:])
    if address in _IPV4_COMPAT:
        # ::N.N.N.N - skip the unspecified address (::), which is also
        # technically inside this /96 but is not an embedded IPv4 wrapper.
        embedded = ipaddress.IPv4Address(address.packed[-4:])
        if int(embedded) != 0:
            return embedded
    return address


def _is_public_ip(value: str) -> bool:
    address = _parse_ip(value)
    if address is None:
        return False
    return _is_global_address(address)


def _is_global_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    if (
        isinstance(address, ipaddress.IPv6Address)
        and address in _NAT64_LOCAL_USE_PREFIX
    ):
        # Legacy compatibility: Python before 3.12.4 classified this local-use
        # NAT64 prefix as global. TODO: remove once support for those Python
        # versions is dropped.
        return False
    return _unwrap_ipv6_transition(address).is_global


def validate_runtime_ip(value: str, *, allow_private_targets: bool = True) -> None:
    if allow_private_targets:
        return

    if not _is_public_ip(value):
        raise ValidationError(
            gettext(
                "This URL is prohibited because it points to an internal or non-public address."
            ),
            code="private_target",
        )


def is_allowlisted_hostname(
    hostname: str, allowed_domains: list[str] | tuple[str, ...]
) -> bool:
    return bool(allowed_domains) and validate_host(
        _normalize_hostname(hostname), allowed_domains
    )


def validate_untrusted_hostname(
    hostname: str,
    *,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> None:
    normalized = _normalize_hostname(hostname)
    if not normalized:
        raise ValidationError(
            gettext(
                "This URL is prohibited because it points to an internal or non-public address."
            ),
            code="private_target",
        )

    if is_allowlisted_hostname(normalized, allowed_domains):
        return

    if ip_address := _parse_hostname_ip(normalized):
        if not _is_global_address(ip_address):
            raise ValidationError(
                gettext(
                    "This URL is prohibited because it points to an internal or non-public address."
                ),
                code="private_target",
            )
        return

    lowered = normalized.lower()
    if lowered == "localhost" or lowered.endswith(LOCAL_HOST_SUFFIXES):
        raise ValidationError(
            gettext(
                "This URL is prohibited because it points to an internal or non-public address."
            ),
            code="private_target",
        )
    if "." not in normalized:
        raise ValidationError(
            gettext(
                "This URL is prohibited because it points to an internal or non-public address."
            ),
            code="private_target",
        )


def validate_outbound_url(
    value: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> None:
    if allow_private_targets:
        return

    hostname = urlparse(value).hostname
    if not hostname:
        raise ValidationError(gettext("Could not parse URL."))

    validate_untrusted_hostname(hostname, allowed_domains=allowed_domains)


def validate_outbound_hostname(
    value: str,
    *,
    allow_private_targets: bool = True,
    allowed_domains: list[str] | tuple[str, ...] = (),
) -> None:
    if allow_private_targets:
        return

    validate_untrusted_hostname(value, allowed_domains=allowed_domains)


def validate_runtime_hostname(
    value: str, *, allow_private_targets: bool = True
) -> None:
    if allow_private_targets:
        return

    normalized = _normalize_hostname(value)

    if ip_address := _parse_hostname_ip(normalized):
        validate_runtime_ip(
            str(ip_address), allow_private_targets=allow_private_targets
        )
        return

    try:
        addresses = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as error:
        raise ValidationError(
            gettext("Could not resolve the URL domain: {}").format(error)
        ) from error

    for _family, _type, _proto, _canonname, sockaddr in addresses:
        address = sockaddr[0]
        if isinstance(address, str):
            validate_runtime_ip(address, allow_private_targets=allow_private_targets)


def validate_runtime_url(value: str, *, allow_private_targets: bool = True) -> None:
    if allow_private_targets:
        return

    hostname = urlparse(value).hostname
    if not hostname:
        raise ValidationError(gettext("Could not parse URL."))

    validate_runtime_hostname(hostname, allow_private_targets=allow_private_targets)
