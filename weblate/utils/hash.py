# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from siphashc import siphash

if TYPE_CHECKING:
    from collections.abc import Mapping


def raw_hash(*parts: str) -> int:
    """Calculate checksum identifying translation."""
    if not parts:
        data = ""
    elif len(parts) == 1:
        data = parts[0]
    else:
        data = "".join(part for part in parts)
    return siphash("Weblate Sip Hash", data)


def calculate_dict_hash(data: Mapping[str, Any]) -> int:
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


def calculate_checksum(*parts: str) -> str:
    """Calculate siphashc checksum for given strings."""
    return format(raw_hash(*parts), "016x")


def checksum_to_hash(checksum: str) -> int:
    """Convert hex to id_hash (signed 64-bit int)."""
    return int(checksum, 16) - 2**63


def hash_to_checksum(id_hash: int) -> str:
    """Convert id_hash (signed 64-bit int) to unsigned hex."""
    return format(id_hash + 2**63, "016x")


def calculate_json_fingerprint(context: dict[str, Any]) -> str:
    """
    Hash a JSON context, preserving the format used by stored alert dismissals.

    Historical migrations use this helper too. Keep its serialization stable
    and independent of models or database access.
    """
    serialized = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode()).hexdigest()
