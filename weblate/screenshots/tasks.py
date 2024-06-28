# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path

from celery.schedules import crontab
from django.core.files.storage import DefaultStorage

from weblate.screenshots.models import Screenshot
from weblate.utils.celery import app


@app.task(trail=False)
def cleanup_screenshot_files() -> None:
    """Remove stale screenshots."""
    storage = DefaultStorage()
    try:
        files = storage.listdir("screenshots")[1]
    except OSError:
        return
    for name in files:
        fullname = os.path.join("screenshots", name)
        if not Screenshot.objects.filter(image=fullname).exists():
            storage.delete(fullname)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=35),
        cleanup_screenshot_files.s(),
        name="screenshot-files-cleanup",
    )
