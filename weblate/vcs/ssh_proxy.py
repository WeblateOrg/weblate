# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Connect OpenSSH to validated numeric addresses without another DNS lookup."""

from __future__ import annotations

import argparse
import os
import select
import socket
import sys
from ipaddress import ip_address

CONNECT_TIMEOUT = 20
BUFFER_SIZE = 65536


def connect_to_addresses(
    addresses: list[str], port: int, timeout: int = CONNECT_TIMEOUT
) -> socket.socket:
    """Connect to the first reachable numeric address."""
    last_error: OSError | None = None
    for value in addresses:
        address = ip_address(value)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        connection = socket.socket(family, socket.SOCK_STREAM)
        connection.settimeout(timeout)
        endpoint = (
            (str(address), port, 0, 0) if address.version == 6 else (str(address), port)
        )
        try:
            connection.connect(endpoint)
        except OSError as error:
            connection.close()
            last_error = error
            continue
        connection.settimeout(None)
        return connection

    if last_error is not None:
        raise last_error
    message = "No addresses to connect to"
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
        sys.stderr.write(f"SSH connection failed: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
