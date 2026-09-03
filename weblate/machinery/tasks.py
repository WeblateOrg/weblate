# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from weblate.utils.celery import app


@app.task(trail=False)
def cleanup_machinery_errors() -> None:
    """Cleanup old machinery errors."""
    # ruff: ignore[import-outside-top-level]
    from weblate.machinery.models import MachineryError

    MachineryError.objects.filter(
        timestamp__lt=timezone.now()
        - timedelta(days=settings.MACHINERY_ERROR_KEEP_DAYS)
    ).delete()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        crontab(hour=1, minute=30),
        cleanup_machinery_errors.s(),
        name="cleanup-machinery-errors",
    )
