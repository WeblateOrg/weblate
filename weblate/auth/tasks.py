# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from weblate.accounts.utils import (
    delete_api_tokens,
    is_site_api_token_user,
    remove_user,
)
from weblate.auth.models import Invitation, User
from weblate.utils.celery import app
from weblate.utils.errors import report_error

if TYPE_CHECKING:
    from celery import Celery

LOGGER = logging.getLogger(__name__)


def _disable_expired_user(user: User) -> None:
    if is_site_api_token_user(user):
        # Revoke the key before remove_user commits pending edits.
        delete_api_tokens(user)
        remove_user(user, None, activity="token-removed", method="site")
        return
    # Use save() to create audit log entry
    user.is_active = False
    user.save()


@app.task(trail=False)
def disable_expired() -> None:
    expired_users = User.objects.filter(
        date_expires__lte=timezone.now(), is_active=True
    ).order_by("pk")
    for user in expired_users:
        try:
            _disable_expired_user(user)
        except Exception:
            LOGGER.exception("Could not disable expired account %s", user.pk)
            report_error("Could not disable expired account")


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
