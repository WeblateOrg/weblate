# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.checks.models import CHECKS
from weblate.trans.models import Component
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=60,
)
def batch_update_checks(
    component_id, checks, component: Component | None = None
) -> None:
    if component is None:
        component = Component.objects.get(pk=component_id)
    with component.lock:
        for check in checks:
            check_obj = CHECKS[check]
            component.log_info("batch updating check %s", check)
            check_obj.perform_batch(component)
