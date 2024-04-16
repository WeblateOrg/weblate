# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from weblate.auth.models import Invitation, User
from weblate.utils.celery import app


@app.task(trail=False)
def disable_expired() -> None:
    User.objects.filter(date_expires__lte=timezone.now(), is_active=True).update(
        is_active=False
    )


@app.task(trail=False)
def cleanup_invitations() -> None:
    Invitation.objects.filter(
        timestamp__lte=timezone.now() - timedelta(seconds=settings.AUTH_TOKEN_VALID)
    ).delete()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(3600, disable_expired.s(), name="disable-expired")
    sender.add_periodic_task(
        crontab(hour=6, minute=6), cleanup_invitations.s(), name="cleanup_invitations"
    )
