"""Custom scheduled task."""

from __future__ import annotations

# ruff: ignore[suspicious-subprocess-import]
import subprocess
from typing import TYPE_CHECKING

from celery.schedules import crontab

from weblate.utils.celery import app

if TYPE_CHECKING:
    from celery import Celery


@app.task
def custom_task() -> None:
    """Execute custom task code."""
    # ruff: ignore[start-process-with-partial-path]
    subprocess.run(["sleep", "1"], check=True)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    """Configure when periodic task is triggered."""
    sender.add_periodic_task(
        crontab(hour=1, minute=0), custom_task.s(), name="custom-task"
    )
