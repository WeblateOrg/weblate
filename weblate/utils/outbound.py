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


def _is_public_ip(value: str) -> bool:
    address = _parse_ip(value)
    return address is not None and address.is_global


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
        if not ip_address.is_global:
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
