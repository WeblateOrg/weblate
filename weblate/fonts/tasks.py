# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from celery.schedules import crontab

from weblate.fonts.models import Font
from weblate.fonts.storage import (
    font_storage,
    get_font_cache_dir,
    remove_unused_cached_fonts,
)
from weblate.utils.celery import app

if TYPE_CHECKING:
    from celery import Celery


@app.task(trail=False)
def cleanup_font_files() -> None:
    """Remove stale fonts and unused local copies."""
    cache_dir = get_font_cache_dir()
    if cache_dir.is_dir():
        # Copies of deleted fonts, and of fonts not used recently, which are
        # downloaded again when needed
        remove_unused_cached_fonts(cache_dir.iterdir(), max_age=86400)
    try:
        files = font_storage.listdir("")[1]
    except OSError:
        return
    for name in files:
        if not Font.objects.filter(font=name).exists():
            font_storage.delete(name)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=55), cleanup_font_files.s(), name="font-files-cleanup"
    )
