# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from siphashc import siphash


def raw_hash(*parts: str):
    """Calculates checksum identifying translation."""
    data = "".join(part for part in parts)
    return siphash("Weblate Sip Hash", data)


def calculate_hash(*parts: str):
    """Calculates checksum identifying translation."""
    # Need to convert it from unsigned 64-bit int to signed 64-bit int
    return raw_hash(*parts) - 2**63


def calculate_checksum(*parts: str):
    """Calculates siphashc checksum for given strings."""
    return format(raw_hash(*parts), "016x")


def checksum_to_hash(checksum: str):
    """Converts hex to id_hash (signed 64-bit int)."""
    return int(checksum, 16) - 2**63


def hash_to_checksum(id_hash: int):
    """Converts id_hash (signed 64-bit int) to unsigned hex."""
    return format(id_hash + 2**63, "016x")
