# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess

from celery.schedules import crontab

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.fonts.utils import configure_fontconfig
from weblate.trans.util import get_clean_env
from weblate.utils.celery import app


@app.task(trail=False)
def cleanup_font_files() -> None:
    """Remove stale fonts."""
    try:
        files = FONT_STORAGE.listdir(".")[1]
    except OSError:
        return
    for name in files:
        if name == "fonts.conf":
            continue
        if not Font.objects.filter(font=name).exists():
            FONT_STORAGE.delete(name)


@app.task(trail=False)
def update_fonts_cache() -> None:
    configure_fontconfig()
    subprocess.run(
        ["fc-cache"],
        env=get_clean_env(),
        check=True,
        capture_output=True,
    )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=55), cleanup_font_files.s(), name="font-files-cleanup"
    )
