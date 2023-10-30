# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from datetime import timedelta
from email.mime.image import MIMEImage

import sentry_sdk
from celery.schedules import crontab
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.timezone import now
from html2text import HTML2Text
from social_django.models import Code, Partial

from weblate.utils.celery import app
from weblate.utils.errors import report_error


@app.task(trail=False)
def cleanup_social_auth():
    """Cleanup expired partial social authentications."""
    age = now() - timedelta(seconds=settings.AUTH_TOKEN_VALID)
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


@app.task(trail=False)
def notify_change(change_id):
    from weblate.accounts.notifications import NOTIFICATIONS_ACTIONS
    from weblate.trans.models import Change

    change = Change.objects.get(pk=change_id)
    perm_cache = {}
    if change.action in NOTIFICATIONS_ACTIONS:
        outgoing = []
        for notification_cls in NOTIFICATIONS_ACTIONS[change.action]:
            notification = notification_cls(outgoing, perm_cache)
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
    notify_digest("notify_daily")


@app.task(trail=False)
def notify_weekly():
    notify_digest("notify_weekly")


@app.task(trail=False)
def notify_monthly():
    notify_digest("notify_monthly")


@app.task(trail=False)
def notify_auditlog(log_id, email):
    from weblate.accounts.models import AuditLog
    from weblate.accounts.notifications import send_notification_email

    audit = AuditLog.objects.get(pk=log_id)
    send_notification_email(
        audit.user.profile.language,
        [email],
        "account_activity",
        context={
            "message": audit.get_message,
            "extra_message": audit.get_extra_message,
            "address": audit.address,
            "user_agent": audit.user_agent,
        },
        info=f"{audit.activity} from {audit.address}",
    )


@app.task(trail=False)
def send_mails(mails):
    """Send multiple mails in single connection."""
    images = []
    with sentry_sdk.start_span(op="email.images"):
        for name in ("email-logo.png", "email-logo-footer.png"):
            filename = os.path.join(settings.STATIC_ROOT, name)
            with open(filename, "rb") as handle:
                image = MIMEImage(handle.read())
            image.add_header("Content-ID", f"<{name}@cid.weblate.org>")
            image.add_header("Content-Disposition", "inline", filename=name)
            images.append(image)

    with sentry_sdk.start_span(op="email.connect"):
        connection = get_connection()
        try:
            connection.open()
        except Exception:
            report_error(cause="Could not send notifications")
            connection.close()
            return

    html2text = HTML2Text(bodywidth=78)
    html2text.unicode_snob = True
    html2text.ignore_images = True
    html2text.pad_tables = True

    try:
        for mail in mails:
            with sentry_sdk.start_span(op="email.text"):
                text = html2text.handle(mail["body"])
            email = EmailMultiAlternatives(
                settings.EMAIL_SUBJECT_PREFIX + mail["subject"],
                text,
                to=[mail["address"]],
                headers=mail["headers"],
                connection=connection,
            )
            email.mixed_subtype = "related"
            for image in images:
                email.attach(image)
            email.attach_alternative(mail["body"], "text/html")
            with sentry_sdk.start_span(op="email.send"):
                email.send()
    finally:
        connection.close()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600, cleanup_social_auth.s(), name="social-auth-cleanup")
    sender.add_periodic_task(3600, cleanup_auditlog.s(), name="auditlog-cleanup")
    sender.add_periodic_task(
        crontab(hour=1, minute=0), notify_daily.s(), name="notify-daily"
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week="mon"),
        notify_weekly.s(),
        name="notify-weekly",
    )
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day_of_month=1),
        notify_monthly.s(),
        name="notify-monthly",
    )
