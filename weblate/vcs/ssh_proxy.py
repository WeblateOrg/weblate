# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Connect OpenSSH to validated numeric addresses without another DNS lookup."""

from __future__ import annotations

import argparse
import errno
import os
import select
import socket
import sys
from ipaddress import ip_address
from itertools import zip_longest
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

# Leave time to report failures before the SSH wrapper's 20-second timeout.
CONNECT_TIMEOUT = 15
CONNECT_DELAY = 0.25
BUFFER_SIZE = 65536


def start_connection(address: IPv4Address | IPv6Address, port: int) -> socket.socket:
    """Start a nonblocking connection without resolving the address again."""
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    endpoint = (
        (str(address), port, 0, 0) if address.version == 6 else (str(address), port)
    )
    connection = socket.socket(family, socket.SOCK_STREAM)
    try:
        connection.setblocking(False)
        error = connection.connect_ex(endpoint)
    except OSError:
        connection.close()
        raise
    if error not in {0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EINTR}:
        connection.close()
        raise OSError(error, os.strerror(error))
    return connection


def connect_to_addresses(
    addresses: list[str], port: int, timeout: int = CONNECT_TIMEOUT
) -> socket.socket:
    """Race staggered connections to validated addresses within one timeout."""
    parsed = [ip_address(value) for value in addresses]
    if not parsed:
        message = "No addresses to connect to"
        raise OSError(message)

    # Preserve preference within each family, but try the other family second.
    preferred = [address for address in parsed if address.version == parsed[0].version]
    alternate = [address for address in parsed if address.version != parsed[0].version]
    candidates = [
        address
        for pair in zip_longest(preferred, alternate)
        for address in pair
        if address is not None
    ]
    pending: dict[socket.socket, str] = {}
    deadline = monotonic() + timeout
    next_attempt = monotonic()
    last_error: OSError | None = None
    failures: dict[str, str] = {}
    try:
        while candidates or pending:
            now = monotonic()
            if now >= deadline:
                details = "\n".join(
                    f"  {host}: {reason}" for host, reason in failures.items()
                )
                message = (
                    f"Timed out connecting to validated SSH addresses after {timeout} seconds.\n"
                    f"{details}"
                )
                raise TimeoutError(message)
            if candidates and (not pending or now >= next_attempt):
                address = candidates.pop(0)
                failures[str(address)] = "Connection timed out"
                try:
                    pending[start_connection(address, port)] = str(address)
                except OSError as connection_error:
                    last_error = connection_error
                    failures[str(address)] = str(connection_error)
                    continue
                next_attempt = monotonic() + CONNECT_DELAY

            wait = deadline - monotonic()
            if candidates:
                wait = min(wait, next_attempt - monotonic())
            _, writable, _ = select.select([], list(pending), [], max(0, wait))
            for connection in writable:
                error = connection.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if error:
                    last_error = OSError(error, os.strerror(error))
                    failures[pending.pop(connection)] = str(last_error)
                    connection.close()
                    # An explicit failure should not delay the next attempt.
                    next_attempt = monotonic()
                    continue
                connection.setblocking(True)
                del pending[connection]
                return connection
    finally:
        for connection in pending:
            connection.close()

    if last_error is not None:
        details = "\n".join(f"  {host}: {reason}" for host, reason in failures.items())
        raise OSError(
            last_error.errno,
            f"Could not connect to any validated SSH address.\n{details}",
        )
    message = "No reachable SSH addresses"
    raise OSError(message)


def write_all(file_descriptor: int, data: bytes) -> None:
    """Write all data to a file descriptor."""
    while data:
        written = os.write(file_descriptor, data)
        data = data[written:]


def relay(connection: socket.socket) -> None:
    """Relay data between OpenSSH and the connected socket."""
    stdin = sys.stdin.fileno()
    stdout = sys.stdout.fileno()
    inputs: list[int | socket.socket] = [connection, stdin]

    while connection in inputs:
        readable, _writable, _exceptional = select.select(inputs, [], [])
        for source in readable:
            if source is connection:
                data = connection.recv(BUFFER_SIZE)
                if not data:
                    return
                write_all(stdout, data)
                continue

            data = os.read(stdin, BUFFER_SIZE)
            if data:
                connection.sendall(data)
            else:
                inputs.remove(stdin)
                connection.shutdown(socket.SHUT_WR)


def main() -> int:
    """Run the SSH proxy."""
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("addresses", nargs="+")
    arguments = parser.parse_args()

    try:
        connection = connect_to_addresses(arguments.addresses, arguments.port)
        with connection:
            relay(connection)
    except (OSError, ValueError) as error:
        sys.stderr.write(
            f"SSH proxy connection failed on port {arguments.port}: {error}\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
