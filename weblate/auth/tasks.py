# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils import timezone

from weblate.auth.models import User
from weblate.utils.celery import app


@app.task(trail=False)
def disable_expired():
    User.objects.filter(date_expires__lte=timezone.now(), is_active=True).update(
        is_active=False
    )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600, disable_expired.s(), name="disable-expired")
