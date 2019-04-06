# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import absolute_import, unicode_literals

from datetime import timedelta
import time

from celery.schedules import crontab

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import get_connection
from django.utils.timezone import now

from social_django.models import Partial, Code

from weblate.celery import app


@app.task
def cleanup_social_auth():
    """Cleanup expired partial social authentications."""
    for partial in Partial.objects.all():
        kwargs = partial.data['kwargs']
        if ('weblate_expires' not in kwargs or
                kwargs['weblate_expires'] < time.time()):
            # Old entry without expiry set, or expired entry
            partial.delete()

    age = now() + timedelta(seconds=settings.AUTH_TOKEN_VALID)
    # Delete old not verified codes
    Code.objects.filter(
        verified=False,
        timestamp__lt=age
    ).delete()

    # Delete old partial data
    Partial.objects.filter(
        timestamp__lt=age
    ).delete()


@app.task
def cleanup_auditlog():
    """Cleanup old auditlog entries."""
    from weblate.accounts.models import AuditLog
    AuditLog.objects.filter(
        timestamp__lt=now() - timedelta(days=settings.AUDITLOG_EXPIRY)
    ).delete()


# Retry for not existing object (maybe transaction not yet committed) with
# delay of 10 minutes growing exponentially
@app.task(autoretry_for=(ObjectDoesNotExist,), retry_backoff=600)
def notify_change(change_id):
    from weblate.trans.models import Change
    from weblate.accounts.notifications import NOTIFICATIONS_ACTIONS
    change = Change.objects.get(pk=change_id)
    if change.action in NOTIFICATIONS_ACTIONS:
        with get_connection() as connection:
            for notification_cls in NOTIFICATIONS_ACTIONS[change.action]:
                notification = notification_cls(connection)
                notification.notify_immediate(change)


def notify_digest(method):
    from weblate.accounts.notifications import NOTIFICATIONS
    with get_connection() as connection:
        for notification_cls in NOTIFICATIONS:
            notification = notification_cls(connection)
            getattr(notification, method)()


@app.task
def notify_daily():
    notify_digest('notify_daily')


@app.task
def notify_weekly():
    notify_digest('notify_weekly')


@app.task
def notify_monthly():
    notify_digest('notify_monthly')


@app.task(autoretry_for=(ObjectDoesNotExist,))
def notify_auditlog(log_id):
    from weblate.accounts.models import AuditLog
    from weblate.accounts.notifications import send_notification_email
    audit = AuditLog.objects.get(pk=log_id)
    send_notification_email(
        audit.user.profile.language,
        audit.user.email,
        'account_activity',
        context={
            'message': audit.get_message,
            'extra_message': audit.get_extra_message,
            'address': audit.address,
            'user_agent': audit.user_agent,
        },
        info='{0} from {1}'.format(audit.activity, audit.address),
    )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600,
        cleanup_social_auth.s(),
        name='social-auth-cleanup',
    )
    sender.add_periodic_task(
        3600,
        cleanup_auditlog.s(),
        name='auditlog-cleanup',
    )
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        notify_daily.s(),
        name='notify-daily',
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week='monday'),
        notify_weekly.s(),
        name='notify-weekly',
    )
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day=1),
        notify_monthly.s(),
        name='notify-monthly',
    )
