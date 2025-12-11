# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from celery.schedules import crontab

from weblate.gitexport.models import update_all_components
from weblate.utils.celery import app


@app.task(trail=False)
def update_gitexport_urls() -> None:
    update_all_components()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(
        crontab(hour=0, minute=40),
        update_gitexport_urls.s(),
        name="update_gitexport_urls",
    )
