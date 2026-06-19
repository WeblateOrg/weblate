# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from django.apps import AppConfig
from django.core.management.base import CommandError
from django.db.models.signals import post_migrate
from kombu.exceptions import OperationalError


class MemoryConfig(AppConfig):
    name = "weblate.memory"
    label = "memory"
    verbose_name = "Translation Memory"

    def ready(self) -> None:
        super().ready()
        post_migrate.connect(self.post_migrate, sender=self)

    def post_migrate(self, sender: AppConfig, **kwargs) -> None:
        # TODO(2028.1): Remove this background TM scope backfill scheduling once
        # Weblate no longer supports direct upgrades from 2026 releases.
        # ruff: ignore[import-outside-top-level]
        from weblate.memory.models import (
            Memory,
            MemoryScopeMigrationState,
        )
        from weblate.memory.tasks import (  # noqa: PLC0415
            backfill_memory_scopes,
            compact_memory_scopes,
        )

        if Memory.objects.exists():
            backfill_completed = MemoryScopeMigrationState.objects.filter(
                name="memory-scope-backfill",
                completed=True,
            ).exists()
            try:
                if backfill_completed:
                    compact_memory_scopes.delay()
                else:
                    backfill_memory_scopes.delay()
            except OperationalError as error:
                msg = (
                    "Could not schedule translation memory scope migration task. "
                    "Make sure the Celery broker is running during Weblate "
                    "upgrade, then rerun migrations."
                )
                raise CommandError(msg) from error
