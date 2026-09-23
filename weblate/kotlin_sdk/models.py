# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from collections.abc import Iterable


class KotlinSDKCleanup(models.Model):
    """Internal deletion intent for a retired manifest or uninstalled add-on."""

    path = models.TextField(unique=True)
    build = models.OneToOneField(
        "KotlinSDKBuild", on_delete=models.SET_NULL, null=True, related_name="cleanup"
    )

    def __str__(self) -> str:
        return self.path


class KotlinSDKBuild(models.Model):
    addon = models.ForeignKey(
        "addons.Addon", on_delete=models.CASCADE, related_name="sdk_builds"
    )
    package_name = models.CharField(max_length=127)
    version_code = models.PositiveBigIntegerField()
    metadata = models.JSONField(default=dict)
    # Durable publication intent; not part of the registration API.
    pending_manifest = models.JSONField(default=dict)
    digest = models.CharField(max_length=64)
    created = models.DateTimeField(auto_now_add=True)
    retired = models.DateTimeField(null=True)
    status = models.CharField(max_length=16, default="pending")
    error = models.TextField(blank=True)
    published = models.DateTimeField(null=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("addon", "package_name", "version_code"),
                name="kotlin_sdk_build_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.package_name}/{self.version_code}"

    def set_artifacts(
        self, artifacts: Iterable[KotlinSDKArtifact], *, append: bool = False
    ) -> None:
        """Change references and start grace while the caller holds the add-on lock."""
        previous = set(self.artifacts.values_list("pk", flat=True))
        requested = {artifact.pk for artifact in artifacts}
        added = requested - previous
        removed = set() if append else previous - requested
        if added:
            self.artifacts.add(*added)
        if removed:
            self.artifacts.remove(*removed)
        tracked = KotlinSDKArtifact.objects.using(self._state.db).filter(
            addon_id=self.addon_id
        )
        tracked.filter(pk__in=added, unreferenced__isnull=False).update(
            unreferenced=None
        )
        tracked.filter(
            pk__in=removed, builds__isnull=True, unreferenced__isnull=True
        ).update(unreferenced=timezone.now())


class KotlinSDKArtifact(models.Model):
    addon = models.ForeignKey(
        "addons.Addon", on_delete=models.CASCADE, related_name="sdk_artifacts"
    )
    digest = models.CharField(max_length=64)
    unreferenced = models.DateTimeField(null=True)
    builds = models.ManyToManyField(KotlinSDKBuild, related_name="artifacts")

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=("addon", "digest"), name="kotlin_sdk_artifact_unique"
            )
        ]

    def __str__(self) -> str:
        return self.digest
