# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.automation.runner import run_automation
from weblate.utils.celery import app


@app.task(trail=False)
def automation_run(activity_id: int) -> None:
    run_automation(activity_id)
