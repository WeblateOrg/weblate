# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.utils.celery import app
from weblate.vcs.pending import cleanup_pending_github_installations

if TYPE_CHECKING:
    from celery import Celery


@app.task(trail=False)
def cleanup_pending_installations() -> None:
    """Remove expired pending code-hosting installation webhook payloads."""
    cleanup_pending_github_installations()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        15 * 60,
        cleanup_pending_installations.s(),
        name="cleanup-pending-installations",
    )
