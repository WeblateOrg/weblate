#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import sys
from hashlib import sha1
from uuid import UUID


def generate_uuid(payload: str) -> UUID:
    """
    Generate a UUID from the SHA-1 hash of bytes.

    This is essentially uuid.uuid5 without requiring a namespace.
    """
    digest = sha1(payload.encode(), usedforsecurity=False).digest()
    return UUID(bytes=digest[:16], version=5)


if len(sys.argv) != 2:
    print("Usage: reproducible-sbom.py sbom.json")
    sys.exit(1)

filename = sys.argv[1]
with open(filename) as handle:
    data = json.load(handle)

# Remove varying fields
data["metadata"].pop("timestamp", None)

# Generate UUID based on the content (with serialNumber excluded)
checksum_data = data.copy()
checksum_data.pop("serialNumber", None)
reproducible_uuid = generate_uuid(json.dumps(checksum_data))

# Update serial number
data["serialNumber"] = f"urn:uuid:{reproducible_uuid}"

with open(filename, "w") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
