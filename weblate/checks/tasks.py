# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.checks.models import CHECKS
from weblate.trans.models import Component
from weblate.utils.celery import app


@app.task(trail=False)
def batch_update_checks(component_id, checks):
    component = Component.objects.get(pk=component_id)
    for check in checks:
        check_obj = CHECKS[check]
        check_obj.perform_batch(component)
