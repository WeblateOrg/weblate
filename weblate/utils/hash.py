# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from siphashc import siphash


def raw_hash(*parts: str) -> int:
    """Calculate checksum identifying translation."""
    if not parts:
        data = ""
    elif len(parts) == 1:
        data = parts[0]
    else:
        data = "".join(part for part in parts)
    return siphash("Weblate Sip Hash", data)


def calculate_dict_hash(data: dict) -> int:
    """
    Calculate checksum of a dict.

    * Ordering independent.
    * Coerces all values to string.

    Returns unsigned int.
    """
    return raw_hash(*(f"{part[0]}:{part[1]}" for part in sorted(data.items())))


def calculate_hash(*parts: str) -> int:
    """Calculate checksum identifying translation."""
    # Need to convert it from unsigned 64-bit int to signed 64-bit int
    return raw_hash(*parts) - 2**63


def calculate_checksum(*parts: str):
    """Calculate siphashc checksum for given strings."""
    return format(raw_hash(*parts), "016x")


def checksum_to_hash(checksum: str):
    """Convert hex to id_hash (signed 64-bit int)."""
    return int(checksum, 16) - 2**63


def hash_to_checksum(id_hash: int):
    """Convert id_hash (signed 64-bit int) to unsigned hex."""
    return format(id_hash + 2**63, "016x")
