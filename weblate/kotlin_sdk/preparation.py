# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prepare one resource mapping at a time, reusing output across versions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from arsc_writer import generate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from arsc_writer import ResourceTable, ResourceValue

    from weblate.kotlin_sdk.models import KotlinSDKBuild
    from weblate.kotlin_sdk.translations import LocaleSnapshot


@dataclass(frozen=True)
class BuildInput:
    pk: int
    digest: str
    package_name: str
    version_code: int

    @classmethod
    def capture(cls, build: KotlinSDKBuild) -> BuildInput:
        return cls(build.pk, build.digest, build.package_name, build.version_code)


def resource_mapping(build: KotlinSDKBuild) -> dict[str, Any]:
    return {
        "packageName": build.package_name,
        "strings": build.metadata["strings"],
        "plurals": build.metadata["plurals"],
    }


def mapping_digest(mapping: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass
class PreparedPublication:
    locales: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, tuple[Path, int]] = field(default_factory=dict)

    def manifest(self, build: BuildInput) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "packageName": build.package_name,
            "versionCode": build.version_code,
            "locales": self.locales,
        }


def resource_size(name: str, value: ResourceValue) -> int:
    return (
        128
        + 4 * len(name)
        + sum(
            64
            + 4 * len(text.value)
            + sum(32 + 4 * len(tag) for tag, _, _ in text.spans)
            for text in (value.values() if isinstance(value, dict) else (value,))
        )
    )


def prepare(
    mapping: dict[str, Any],
    directory: Path,
    translations: Callable[[set[tuple[str, str]]], Iterable[LocaleSnapshot]],
    compilation_limit: int,
    staging_limit: int,
    *,
    renew_lock: Callable[[], None] | None = None,
) -> PreparedPublication:
    result = PreparedPublication()
    keys = {(kind, name) for kind in ("strings", "plurals") for name in mapping[kind]}
    staged_size = 0
    for language, (locale, entries) in translations(keys):
        if renew_lock is not None:
            renew_lock()
        resources: ResourceTable = {}
        estimated = 4096
        records = iter(entries)
        try:
            for (kind, name), value in records:
                if (kind, name) not in keys:
                    continue
                estimated += resource_size(name, value)
                if estimated > compilation_limit:
                    msg = "Kotlin SDK per-locale compilation estimate exceeds 64 MiB."
                    raise ValueError(msg)
                resources[int(mapping[kind][name], 16)] = (name, value)
        finally:
            if isinstance(records, Generator):
                records.close()
        if not resources:
            continue
        content = generate(resources, package=mapping["packageName"], locale=locale)
        del resources
        digest = hashlib.sha256(content).hexdigest()
        if digest not in result.outputs:
            if staged_size + len(content) > staging_limit:
                msg = "Kotlin SDK temporary storage limit reached."
                raise ValueError(msg)
            path = directory / f"{digest}.arsc"
            path.write_bytes(content)
            result.outputs[digest] = (path, len(content))
            staged_size += len(content)
        result.locales[language] = {
            "url": f"../../artifacts/{digest}.arsc",
            "sha256": digest,
            "size": len(content),
        }
        del content
    return result
