# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures for tests with mocked external services."""

from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Generator


type AddressInfo = tuple[
    socket.AddressFamily,
    socket.SocketKind,
    int,
    str,
    tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
]


@contextmanager
def mock_dns(*hosts: str) -> Generator[None, None, None]:
    """Give selected mocked service hosts a public address without live DNS."""
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(
        host: str, port: str | int | None, *args: int, **kwargs: int
    ) -> list[AddressInfo]:
        if host in hosts:
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                )
            ]
        return original_getaddrinfo(host, port, *args, **kwargs)

    with patch("weblate.utils.outbound.socket.getaddrinfo", side_effect=getaddrinfo):
        yield
