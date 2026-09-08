# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from celery.schedules import crontab

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.utils.celery import app

if TYPE_CHECKING:
    from celery import Celery


@app.task(trail=False)
def cleanup_font_files() -> None:
    """Remove stale fonts."""
    try:
        files = FONT_STORAGE.listdir(".")[1]
    except OSError:
        return
    for name in files:
        if not Font.objects.filter(font=name).exists():
            FONT_STORAGE.delete(name)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=55), cleanup_font_files.s(), name="font-files-cleanup"
    )
