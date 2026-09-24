# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from weblate.auth.models import Invitation, User
from weblate.utils.celery import app

if TYPE_CHECKING:
    from celery import Celery


@app.task(trail=False)
def disable_expired() -> None:
    for user in User.objects.filter(date_expires__lte=timezone.now(), is_active=True):
        # Use save() to create audit log entry
        user.is_active = False
        user.save()


@app.task(trail=False)
def cleanup_invitations() -> None:
    Invitation.objects.filter(
        timestamp__lte=timezone.now() - timedelta(seconds=settings.AUTH_TOKEN_VALID)
    ).delete()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(3600, disable_expired.s(), name="disable-expired")
    sender.add_periodic_task(
        crontab(hour=6, minute=6), cleanup_invitations.s(), name="cleanup_invitations"
    )
