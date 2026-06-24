#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from uuid import UUID

WEBLATE_ORGANIZATION = {
    "name": "Weblate s.r.o.",
    "url": ["https://weblate.org/"],
}
WEBLATE_AUTHOR = {
    "name": "Weblate s.r.o.",
    "email": "info@weblate.org",
}
GENERATION_CONTEXT_PROPERTY = "cisa:minimum-elements:generation-context"
GENERATION_CONTEXT = "during release build"
GENERATION_LIFECYCLE = {"phase": "build"}


class SBOMValidationError(ValueError):
    """Raised when SBOM metadata does not include required release information."""


def generate_uuid(payload: str) -> UUID:
    """
    Generate a UUID from the SHA-1 hash of bytes.

    This is essentially uuid.uuid5 without requiring a namespace.
    """
    digest = sha1(payload.encode(), usedforsecurity=False).digest()
    return UUID(bytes=digest[:16], version=5)


def format_timestamp(source_date_epoch: str | None) -> str | None:
    if source_date_epoch is None:
        return None
    try:
        timestamp = datetime.fromtimestamp(int(source_date_epoch), UTC)
    except ValueError as error:
        msg = "SOURCE_DATE_EPOCH has to be an integer"
        raise SBOMValidationError(msg) from error
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def find_weblate_component(data: dict) -> dict | None:
    for component in data.get("components", []):
        if component.get("name") == "weblate":
            return copy.deepcopy(component)
    return None


def set_generation_context(metadata: dict) -> None:
    properties = [
        property_
        for property_ in metadata.get("properties", [])
        if property_.get("name") != GENERATION_CONTEXT_PROPERTY
    ]
    properties.append(
        {
            "name": GENERATION_CONTEXT_PROPERTY,
            "value": GENERATION_CONTEXT,
        }
    )
    metadata["properties"] = properties


def update_sbom(data: dict, source_date_epoch: str | None = None) -> None:
    """Update document-level SBOM metadata for release publication."""
    metadata = data.setdefault("metadata", {})
    timestamp = format_timestamp(source_date_epoch)
    if timestamp is not None:
        metadata["timestamp"] = timestamp

    component = find_weblate_component(data)
    if component is not None:
        component["type"] = "application"
        component.setdefault("manufacturer", copy.deepcopy(WEBLATE_ORGANIZATION))
        component.setdefault("supplier", copy.deepcopy(WEBLATE_ORGANIZATION))
        if "purl" not in component and "version" in component:
            component["purl"] = f"pkg:pypi/weblate@{component['version']}"
        metadata["component"] = component

    metadata["authors"] = [copy.deepcopy(WEBLATE_AUTHOR)]
    metadata["manufacturer"] = copy.deepcopy(WEBLATE_ORGANIZATION)
    metadata["supplier"] = copy.deepcopy(WEBLATE_ORGANIZATION)
    metadata["lifecycles"] = [copy.deepcopy(GENERATION_LIFECYCLE)]
    set_generation_context(metadata)

    checksum_data = copy.deepcopy(data)
    checksum_data.pop("serialNumber", None)
    reproducible_uuid = generate_uuid(
        json.dumps(checksum_data, separators=(",", ":"), sort_keys=True)
    )
    data["serialNumber"] = f"urn:uuid:{reproducible_uuid}"


def validate_sbom(data: dict) -> None:
    metadata = data.get("metadata", {})
    errors = []

    if data.get("bomFormat") != "CycloneDX":
        errors.append("SBOM has to use CycloneDX format")
    if not data.get("specVersion"):
        errors.append("SBOM has to include CycloneDX specVersion")
    if not data.get("serialNumber"):
        errors.append("SBOM has to include serialNumber")
    if not metadata.get("timestamp"):
        errors.append("SBOM metadata has to include timestamp")
    if not metadata.get("tools"):
        errors.append("SBOM metadata has to include generation tools")
    if not metadata.get("authors"):
        errors.append("SBOM metadata has to include SBOM author")
    if not metadata.get("supplier") and not metadata.get("manufacturer"):
        errors.append("SBOM metadata has to include software producer")

    component = metadata.get("component", {})
    if component.get("name") != "weblate":
        errors.append("SBOM metadata component has to identify Weblate")
    elif not component.get("version"):
        errors.append("SBOM metadata component has to include Weblate version")

    properties = metadata.get("properties", [])
    if not any(
        property_.get("name") == GENERATION_CONTEXT_PROPERTY and property_.get("value")
        for property_ in properties
    ):
        errors.append("SBOM metadata has to include generation context")

    if errors:
        raise SBOMValidationError("\n".join(errors))


def process_sbom(filename: Path) -> None:
    with filename.open(encoding="utf-8") as handle:
        data = json.load(handle)

    update_sbom(data, os.environ.get("SOURCE_DATE_EPOCH"))
    validate_sbom(data)

    with filename.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        process_sbom(args.filename)
    except SBOMValidationError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
