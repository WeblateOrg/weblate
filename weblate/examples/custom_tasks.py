"""Custom scheduled task."""

import subprocess

from celery.schedules import crontab

from weblate.utils.celery import app


@app.task
def custom_task() -> None:
    """Execute custom task code."""
    subprocess.run(["sleep", "1"], check=True)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    """Configure when periodic task is triggered."""
    sender.add_periodic_task(
        crontab(hour=1, minute=0), custom_task.s(), name="custom-task"
    )
