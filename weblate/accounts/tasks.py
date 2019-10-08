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

import os
import time
from datetime import timedelta
from email.mime.image import MIMEImage

from celery.schedules import crontab
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.timezone import now
from html2text import html2text
from social_django.models import Code, Partial

from weblate.celery import app
from weblate.utils.errors import report_error


@app.task(trail=False)
def cleanup_social_auth():
    """Cleanup expired partial social authentications."""
    for partial in Partial.objects.iterator():
        kwargs = partial.data['kwargs']
        if 'weblate_expires' not in kwargs or kwargs['weblate_expires'] < time.time():
            # Old entry without expiry set, or expired entry
            partial.delete()

    age = now() + timedelta(seconds=settings.AUTH_TOKEN_VALID)
    # Delete old not verified codes
    Code.objects.filter(verified=False, timestamp__lt=age).delete()

    # Delete old partial data
    Partial.objects.filter(timestamp__lt=age).delete()


@app.task(trail=False)
def cleanup_auditlog():
    """Cleanup old auditlog entries."""
    from weblate.accounts.models import AuditLog

    AuditLog.objects.filter(
        timestamp__lt=now() - timedelta(days=settings.AUDITLOG_EXPIRY)
    ).delete()


# Retry for not existing object (maybe transaction not yet committed) with
# delay of 10 minutes growing exponentially
@app.task(
    trail=False,
    autoretry_for=(ObjectDoesNotExist,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def notify_change(change_id, change_name=''):
    from weblate.trans.models import Change
    from weblate.accounts.notifications import NOTIFICATIONS_ACTIONS

    change = Change.objects.get(pk=change_id)
    if change.action in NOTIFICATIONS_ACTIONS:
        outgoing = []
        for notification_cls in NOTIFICATIONS_ACTIONS[change.action]:
            notification = notification_cls(outgoing)
            notification.notify_immediate(change)
        if outgoing:
            send_mails.delay(outgoing)


def notify_digest(method):
    from weblate.accounts.notifications import NOTIFICATIONS

    outgoing = []
    for notification_cls in NOTIFICATIONS:
        notification = notification_cls(outgoing)
        getattr(notification, method)()
    if outgoing:
        send_mails.delay(outgoing)


@app.task(trail=False)
def notify_daily():
    notify_digest('notify_daily')


@app.task(trail=False)
def notify_weekly():
    notify_digest('notify_weekly')


@app.task(trail=False)
def notify_monthly():
    notify_digest('notify_monthly')


@app.task(trail=False, autoretry_for=(ObjectDoesNotExist,))
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


@app.task(trail=False)
def send_mails(mails):
    """Send multiple mails in single connection."""
    filename = os.path.join(settings.STATIC_ROOT, 'email-logo.png')
    with open(filename, 'rb') as handle:
        image = MIMEImage(handle.read())
    image.add_header('Content-ID', '<email-logo@cid.weblate.org>')
    image.add_header('Content-Disposition', 'inline', filename='weblate.png')

    connection = get_connection()
    try:
        connection.open()
    except Exception as error:
        report_error(error, prefix='Failed to send notifications')
        connection.close()
        return

    try:
        for mail in mails:
            email = EmailMultiAlternatives(
                settings.EMAIL_SUBJECT_PREFIX + mail['subject'],
                html2text(mail['body']),
                to=[mail['address']],
                headers=mail['headers'],
                connection=connection,
            )
            email.mixed_subtype = 'related'
            email.attach(image)
            email.attach_alternative(mail['body'], 'text/html')
            email.send()
    finally:
        connection.close()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600, cleanup_social_auth.s(), name='social-auth-cleanup')
    sender.add_periodic_task(3600, cleanup_auditlog.s(), name='auditlog-cleanup')
    sender.add_periodic_task(
        crontab(hour=1, minute=0), notify_daily.s(), name='notify-daily'
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week='monday'),
        notify_weekly.s(),
        name='notify-weekly',
    )
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day=1), notify_monthly.s(), name='notify-monthly'
    )
