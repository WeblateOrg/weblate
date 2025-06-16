#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import sys
import uuid


class NullNamespace:
    bytes = b""


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
reproducible_uuid = uuid.uuid5(NullNamespace, json.dumps(checksum_data))

# Update serial number
data["serialNumber"] = f"urn:uuid:{reproducible_uuid}"

with open(filename, "w") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
