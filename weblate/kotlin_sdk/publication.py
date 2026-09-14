# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Kotlin SDK publication, retention, and transaction ownership."""

from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from lxml import etree
from translate.storage.base import ParseError as TranslateParseError

from weblate.addons.events import AddonEventOutcome
from weblate.kotlin_sdk.arsc import generate
from weblate.kotlin_sdk.preparation import (
    BuildInput,
    PreparedPublication,
    mapping_digest,
    prepare,
    resource_mapping,
)
from weblate.kotlin_sdk.retention import select_retired_builds
from weblate.kotlin_sdk.translations import extract_translations
from weblate.trans.exceptions import FileParseError

if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.addons.models import Addon
    from weblate.kotlin_sdk.addons import KotlinSDKAddon
    from weblate.kotlin_sdk.models import KotlinSDKBuild
    from weblate.kotlin_sdk.translations import LocaleSnapshot

MAX_ARTIFACT_BYTES = 5 * 1024 * 1024 * 1024
MAX_ARTIFACT_FILES = 10000
MAX_PREPARATION_BYTES = 5 * 1024 * 1024 * 1024
MAX_COMPILATION_BYTES = 64 * 1024 * 1024
STAGING_DIRECTORY = ".kotlin-sdk-staging"
ARTIFACT_GRACE = timedelta(hours=24)
RETIRED_RECORD_RETENTION = timedelta(hours=24)


@dataclass
class ArtifactInventory:
    sizes: dict[str, int] = field(default_factory=dict)
    total: int = 0


class Publication:
    def __init__(self, instance: Addon) -> None:
        self.instance = instance
        self.errors: list[str] = []
        self.inventory: ArtifactInventory | None = None

    @property
    def cdn(self) -> KotlinSDKAddon:
        return cast("KotlinSDKAddon", self.instance.addon)

    def schedule(self) -> None:
        from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]
        from weblate.kotlin_sdk.tasks import publish_kotlin_sdk  # ruff: ignore[import-outside-top-level]

        with transaction.atomic():
            current = Addon.objects.select_for_update().get(pk=self.instance.pk)
            pending = current.state.get("kotlin_pending")
            # Recover a request whose broker delivery or worker was lost.
            if pending and timezone.now().timestamp() - pending < 3600:
                return
            current.state["kotlin_pending"] = timezone.now().timestamp()
            Addon.objects.filter(pk=current.pk).update(state=current.state)
            publish_kotlin_sdk.delay_on_commit(current.pk)

    @property
    def staging_path(self) -> Path:
        return (
            Path(settings.LOCALIZE_CDN_PATH)
            / STAGING_DIRECTORY
            / self.instance.state["uuid"]
        )

    def translations(
        self, resource_keys: set[tuple[str, str]] | None = None
    ) -> Generator[LocaleSnapshot]:
        component = self.instance.component
        if component is None:
            return
        yield from extract_translations(component, resource_keys)

    @contextmanager
    def locked_addon(self) -> Generator[Addon | None]:
        from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]

        with transaction.atomic():
            addon = (
                Addon.objects.select_for_update().filter(pk=self.instance.pk).first()
            )
            if (
                addon is None
                or not addon.is_valid
                or addon.name != self.instance.name
                or addon.component_id != self.instance.component_id
                or addon.state.get("uuid") != self.instance.state.get("uuid")
                or not addon.addon.can_process(component=addon.component)
            ):
                yield None
                return
            self.instance = addon
            yield addon

    def refresh_inventory(self) -> ArtifactInventory:
        root = Path(self.cdn.cdn_path("artifacts"))
        sizes = (
            {
                path.name: path.stat().st_size
                for path in root.iterdir()
                if path.is_file()
            }
            if root.exists()
            else {}
        )
        self.inventory = ArtifactInventory(sizes, sum(sizes.values()))
        return self.inventory

    def commit(self, build: BuildInput, prepared: PreparedPublication) -> None:
        from weblate.kotlin_sdk.models import KotlinSDKArtifact  # ruff: ignore[import-outside-top-level]

        try:  # ruff: ignore[too-many-statements-in-try-clause]
            with self.locked_addon() as addon:
                if addon is None:
                    return
                current = addon.sdk_builds.filter(
                    pk=build.pk, digest=build.digest, retired__isnull=True
                ).first()
                if current is None or not self.eligible(current):
                    return
                root = Path(self.cdn.cdn_path("artifacts"))
                inventory = self.inventory or self.refresh_inventory()
                # Cleanup can remove old files between build commits. Reconcile
                # reused files, and rescan before rejecting a possibly stale quota.
                for digest in prepared.outputs:
                    name = f"{digest}.arsc"
                    if name in inventory.sizes and not (root / name).exists():
                        inventory = self.refresh_inventory()
                        break
                additions = {
                    f"{digest}.arsc": size
                    for digest, (_, size) in prepared.outputs.items()
                    if f"{digest}.arsc" not in inventory.sizes
                }
                if (
                    inventory.total + sum(additions.values()) > MAX_ARTIFACT_BYTES
                    or len(inventory.sizes) + len(additions) > MAX_ARTIFACT_FILES
                ):
                    inventory = self.refresh_inventory()
                    additions = {
                        f"{digest}.arsc": size
                        for digest, (_, size) in prepared.outputs.items()
                        if f"{digest}.arsc" not in inventory.sizes
                    }
                self.check_artifact_capacity(
                    total=inventory.total + sum(additions.values()),
                    count=len(inventory.sizes) + len(additions),
                )
                root.mkdir(parents=True, exist_ok=True)
                for digest, (path, size) in prepared.outputs.items():
                    target = root / f"{digest}.arsc"
                    if target.name not in inventory.sizes:
                        path.chmod(0o644)
                        os.link(path, target)
                        inventory.sizes[target.name] = size
                        inventory.total += size
                artifacts = {
                    artifact.digest: artifact
                    for artifact in addon.sdk_artifacts.filter(
                        digest__in=prepared.outputs
                    )
                }
                missing = [
                    KotlinSDKArtifact(
                        addon=addon, digest=digest, unreferenced=timezone.now()
                    )
                    for digest in prepared.outputs
                    if digest not in artifacts
                ]
                KotlinSDKArtifact.objects.bulk_create(missing)
                artifacts.update((artifact.digest, artifact) for artifact in missing)
                current.set_artifacts(
                    [artifacts[digest] for digest in prepared.outputs], append=True
                )
                current.pending_manifest = prepared.manifest(build)
                current.status, current.error = "pending", ""
                current.save(update_fields=["pending_manifest", "status", "error"])
                transaction.on_commit(partial(self.finalize, current.pk))
        except Exception:
            # Reconcile filesystem changes after a failed installation attempt.
            self.inventory = None
            raise

    def finalize(self, build_id: int) -> None:
        if error := self.finalize_manifest(build_id):
            self.errors.append(error)

    def finalize_manifest(self, build_id: int) -> str | None:
        """Publish committed intent; retry safely after crashes or filesystem errors."""
        with self.locked_addon() as addon:
            if addon is None:
                return None
            build = addon.sdk_builds.filter(pk=build_id, retired__isnull=True).first()
            if build is None or not build.pending_manifest or not self.eligible(build):
                return None
            manifest = build.pending_manifest
            try:
                for locale in manifest["locales"].values():
                    path = Path(self.cdn.cdn_path(f"artifacts/{locale['sha256']}.arsc"))
                    if path.stat().st_size != locale["size"]:
                        msg = "Staged Kotlin SDK artifact has an invalid size."
                        raise OSError(msg)  # ruff: ignore[raise-within-try]
                self.cdn.write_cdn_text(
                    f"{build.package_name}/{build.version_code}/manifest.json",
                    json.dumps(manifest, sort_keys=True),
                )
            except OSError as error:
                build.status, build.error = "failed", str(error)
                build.save(update_fields=["status", "error"])
                addon.log_warning("Kotlin SDK manifest publication failed: %s", error)
                return str(error)
            build.set_artifacts(
                addon.sdk_artifacts.filter(
                    digest__in=[
                        locale["sha256"] for locale in manifest["locales"].values()
                    ]
                )
            )
            build.pending_manifest = {}
            build.status, build.error = "published", ""
            build.published = timezone.now()
            build.save(
                update_fields=["pending_manifest", "status", "error", "published"]
            )
            self.expire_builds()
        return None

    @staticmethod
    def check_artifact_capacity(*, total: int, count: int) -> None:
        if count > MAX_ARTIFACT_FILES or total > MAX_ARTIFACT_BYTES:
            msg = "Kotlin SDK artifact storage limit reached. Retry after superseded artifacts are cleaned up."
            raise ValueError(msg)

    def cleanup_artifacts(self) -> None:
        now = timezone.now()
        artifacts = self.instance.sdk_artifacts
        for artifact in artifacts.filter(
            builds__isnull=True, unreferenced__lte=now - ARTIFACT_GRACE
        ):
            Path(self.cdn.cdn_path(f"artifacts/{artifact.digest}.arsc")).unlink(
                missing_ok=True
            )
            artifact.delete()
        # A rollback can leave files with no database record. Include them in
        # quota checks until their fixed grace period has elapsed.
        root = Path(self.cdn.cdn_path("artifacts"))
        known = {
            f"{digest}.arsc" for digest in artifacts.values_list("digest", flat=True)
        }
        if root.exists():
            for path in root.iterdir():
                if (
                    path.is_file()
                    and path.name not in known
                    and path.stat().st_mtime <= (now - ARTIFACT_GRACE).timestamp()
                ):
                    path.unlink()

    def expire_builds(self, *, reserve: int = 0) -> None:
        """Apply retention while the caller holds the add-on row lock."""
        now = timezone.now()
        config = self.instance.configuration
        cutoff = now - timedelta(days=max(1, min(config.get("maximum_age", 365), 730)))
        maximum = max(1, min(config.get("maximum_versions", 20), 100))
        builds = list(
            self.instance.sdk_builds.defer("metadata")
            .filter(retired__isnull=True)
            .order_by("-created", "-pk")
        )
        for build in select_retired_builds(
            builds, maximum=maximum, cutoff=cutoff, reserve=reserve
        ):
            self.retire(build, now)
        # Keep the registration and its artifact references until deletion succeeds.
        self.instance.sdk_builds.filter(
            retired__lte=now - RETIRED_RECORD_RETENTION, cleanup__isnull=True
        ).delete()

    def retire(self, build: KotlinSDKBuild, now: datetime) -> None:
        from weblate.kotlin_sdk.tasks import schedule_cleanup  # ruff: ignore[import-outside-top-level]

        build.retired, build.status = now, "retired"
        build.metadata, build.pending_manifest, build.error = {}, {}, ""
        build.save(
            update_fields=[
                "retired",
                "status",
                "metadata",
                "pending_manifest",
                "error",
            ]
        )
        schedule_cleanup(
            Path(
                self.cdn.cdn_path(
                    f"{build.package_name}/{build.version_code}/manifest.json"
                )
            ),
            build=build,
        )

    def eligible(self, build: KotlinSDKBuild) -> bool:
        now = timezone.now()
        age = max(1, min(self.instance.configuration.get("maximum_age", 365), 730))
        if build.created <= now - timedelta(days=age):
            self.retire(build, now)
            return False
        return True

    def fail(self, build: BuildInput, error: str) -> None:
        with self.locked_addon() as addon:
            if addon is None:
                return
            updated = addon.sdk_builds.filter(
                pk=build.pk, retired__isnull=True, digest=build.digest
            ).update(status="failed", error=error)
            if updated:
                self.errors.append(
                    f"{build.package_name}/{build.version_code}: {error}"
                )

    def publish(self) -> AddonEventOutcome | None:
        """Capture, prepare shared mappings, then commit each eligible build."""
        self.errors = []
        self.inventory = None
        with self.locked_addon() as addon:
            if addon is None:
                return None
            self.expire_builds()
            self.cleanup_artifacts()
            if self.staging_path.exists():
                shutil.rmtree(self.staging_path)
            self.staging_path.mkdir(mode=0o700, parents=True, exist_ok=True)
            build_ids = list(
                addon.sdk_builds.filter(retired__isnull=True).values_list(
                    "pk", flat=True
                )
            )

        groups: dict[str, list[BuildInput]] = {}
        for build_id in build_ids:
            with self.locked_addon() as addon:
                if addon is None:
                    break
                build = addon.sdk_builds.filter(
                    pk=build_id, retired__isnull=True
                ).first()
                if build is None:
                    continue
                if build.pending_manifest:
                    transaction.on_commit(partial(self.finalize, build.pk))
            if build.pending_manifest:
                build = self.instance.sdk_builds.filter(
                    pk=build_id, retired__isnull=True
                ).first()
                if build is None or build.pending_manifest:
                    continue
            digest = mapping_digest(resource_mapping(build))
            groups.setdefault(digest, []).append(BuildInput.capture(build))
            del build

        for digest, builds in groups.items():
            self.publish_group(digest, builds)

        with self.locked_addon() as addon:
            if addon is not None:
                self.cleanup_artifacts()
        return AddonEventOutcome.error(result=self.errors) if self.errors else None

    def publish_group(self, digest: str, builds: list[BuildInput]) -> None:
        # Reload only one group's immutable mapping, trying another version if
        # its representative was retired while earlier groups were compiling.
        mapping = None
        for captured in builds:
            with self.locked_addon() as addon:
                if addon is None:
                    return
                build = addon.sdk_builds.filter(
                    pk=captured.pk, digest=captured.digest, retired__isnull=True
                ).first()
                if build is None or not self.eligible(build):
                    continue
                candidate = resource_mapping(build)
                if mapping_digest(candidate) == digest:
                    mapping = candidate
                    temporary = TemporaryDirectory(dir=self.staging_path)
                    break
        if mapping is None:
            return
        with temporary as directory:
            try:
                prepared = prepare(
                    mapping,
                    Path(directory),
                    self.translations,
                    generate,
                    MAX_COMPILATION_BYTES,
                    MAX_PREPARATION_BYTES,
                )
            except (
                ValueError,
                etree.XMLSyntaxError,
                OSError,
                FileParseError,
                TranslateParseError,
            ) as error:
                for captured in builds:
                    self.fail(captured, str(error))
                return
            for captured in builds:
                try:
                    self.commit(captured, prepared)
                except (ValueError, OSError) as error:
                    self.fail(captured, str(error))
