# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from celery.schedules import crontab

from weblate.fonts.models import Font
from weblate.fonts.storage import font_storage, get_font_cache_dir, remove_cached_font
from weblate.utils.celery import app

if TYPE_CHECKING:
    from celery import Celery


@app.task(trail=False)
def cleanup_font_files() -> None:
    """Remove stale fonts and local copies of deleted fonts."""
    cache_dir = get_font_cache_dir()
    if cache_dir.is_dir():
        font_ids = set(Font.objects.values_list("pk", flat=True))
        for path in cache_dir.iterdir():
            font_id = path.name.split("-", 1)[0]
            if font_id.isdigit() and int(font_id) not in font_ids:
                remove_cached_font(int(font_id))
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
