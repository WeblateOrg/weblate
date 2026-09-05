# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from contextlib import closing
from datetime import datetime, timedelta
from email.message import MIMEPart
from itertools import batched
from smtplib import SMTP, SMTPConnectError
from types import MethodType
from typing import TYPE_CHECKING, TypedDict

from celery.schedules import crontab
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend
from django.db import models, transaction
from django.urls import reverse
from django.utils.timezone import now
from social_django.models import Code, Partial

from weblate.utils.celery import app
from weblate.utils.errors import report_error
from weblate.utils.html import HTML2Text
from weblate.utils.icons import load_icon
from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.core.mail.backends.base import BaseEmailBackend
    from django.db.models import QuerySet

    from weblate.accounts.notifications import Notification, NotificationFrequency
    from weblate.trans.models import Project

LOGGER = logging.getLogger("weblate.smtp")

# The batch size needs to be below exim's default connection_max_messages = 500.
EMAIL_BATCH_SIZE = 200


class OutgoingEmail(TypedDict):
    address: str
    subject: str
    body: str
    headers: dict[str, str]


def get_registration_attempt_password_reset_url(activity: str) -> str | None:
    """Return a password reset URL suitable for registration-attempt e-mails."""
    if activity not in {"connect", "register"}:
        return None
    if settings.PASSWORD_RESET_URL:
        return settings.PASSWORD_RESET_URL

    # ruff: ignore[import-outside-top-level]
    from weblate.auth.utils import (
        get_auth_keys,
    )

    if "email" in get_auth_keys():
        return reverse("password_reset")
    return None


@app.task(trail=False)
def cleanup_social_auth() -> None:
    """Cleanup expired partial social authentications."""
    age = now() - timedelta(seconds=settings.AUTH_TOKEN_VALID)
    # Delete old not verified codes
    Code.objects.filter(verified=False, timestamp__lt=age).delete()

    # Delete old partial data
    Partial.objects.filter(timestamp__lt=age).delete()


@app.task(trail=False)
def cleanup_totp_enrollments() -> None:
    """Remove abandoned enrollments without racing device confirmation."""
    # ruff: ignore[import-outside-top-level]
    from django_otp.plugins.otp_totp.models import TOTPDevice

    # ruff: ignore[import-outside-top-level]
    from weblate.accounts.utils import TOTP_ENROLLMENT_SECONDS

    # ruff: ignore[import-outside-top-level]
    from weblate.auth.models import User

    expired = TOTPDevice.objects.filter(confirmed=False).filter(
        models.Q(created_at__lte=now() - timedelta(seconds=TOTP_ENROLLMENT_SECONDS))
        | models.Q(created_at__isnull=True)
    )
    user_ids = expired.order_by().values_list("user_id", flat=True).distinct()
    for user_id in user_ids.iterator():
        with transaction.atomic():
            if User.objects.select_for_update().filter(pk=user_id).first() is not None:
                expired.filter(user_id=user_id).delete()


@app.task(trail=False)
def cleanup_auditlog() -> None:
    """Cleanup old auditlog entries."""
    # ruff: ignore[import-outside-top-level]
    from weblate.accounts.models import (
        AuditLog,
    )

    timestamp = now()

    # Cleanup old entries
    AuditLog.objects.filter(
        timestamp__lt=timestamp - timedelta(days=settings.AUDITLOG_EXPIRY)
    ).delete()

    # Finalize pending two-factor entries, these happen due to
    # WebAuthn keys being added in two stages. Mature entries older than 5 minutes
    # but look only two hours into past for performance reasons
    for audit in AuditLog.objects.filter(
        timestamp__range=(
            timestamp - timedelta(hours=2),
            timestamp - timedelta(minutes=5),
        ),
        activity="twofactor-add",
    ):
        if "skip_notify" in audit.params:
            del audit.params["skip_notify"]
            audit.save(update_fields=["params"])


class NotificationFactory:
    def __init__(self) -> None:
        self.outgoing: list[OutgoingEmail] = []
        self.instances: dict[str, Notification] = {}

    def for_action(self, action: int) -> Generator[Notification]:
        from weblate.accounts.notifications import (  # ruff: ignore[import-outside-top-level]
            NOTIFICATIONS_ACTIONS,
        )

        if action not in NOTIFICATIONS_ACTIONS:
            return
        for notification_cls in NOTIFICATIONS_ACTIONS[action]:
            name = notification_cls.get_name()
            try:
                yield self.instances[name]
            except KeyError:
                result = self.instances[name] = notification_cls(self.outgoing)
                yield result

    def send_queued(self) -> None:
        if self.outgoing:
            queue_mails(self.outgoing)
            self.outgoing.clear()


@app.task(trail=False)
@transaction.atomic
def notify_changes(change_ids: list[int]) -> None:
    from weblate.trans.models import Change  # ruff: ignore[import-outside-top-level]

    changes = Change.objects.prefetch_for_render().filter(pk__in=change_ids)
    factory = NotificationFactory()

    for change in changes.iterator(chunk_size=200):
        change.fill_in_prefetched()
        for notification in factory.for_action(change.action):
            notification.notify_immediate(change)
        factory.send_queued()


def get_digest_projects(
    notification: type[Notification],
    frequency: NotificationFrequency,
    *,
    since: datetime,
    until: datetime,
    user_ids: list[int] | None = None,
) -> QuerySet[Project]:
    """Return projects which can have recipients for a periodic notification."""
    from weblate.accounts.models import (  # ruff: ignore[import-outside-top-level]
        Subscription,
    )
    from weblate.accounts.notifications import (  # ruff: ignore[import-outside-top-level]
        NotificationScope,
    )
    from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
        Change,
        Project,
    )

    subscriptions = Subscription.objects.filter(
        notification=notification.get_name(),
        frequency=frequency,
        user__is_active=True,
        user__is_bot=False,
    )
    if user_ids is not None:
        subscriptions = subscriptions.filter(user_id__in=user_ids)
    if subscriptions.filter(scope=NotificationScope.SCOPE_ALL).exists():
        projects = Project.objects.all()
    else:
        query = models.Q(
            pk__in=subscriptions.filter(
                project__isnull=False,
            ).values("project_id")
        ) | models.Q(
            pk__in=subscriptions.filter(
                scope=NotificationScope.SCOPE_COMPONENT,
                component__isnull=False,
            ).values("component__project_id")
        )
        if not notification.ignore_watched:
            query |= models.Q(
                pk__in=subscriptions.filter(
                    scope=NotificationScope.SCOPE_WATCHED,
                    user__profile__watched__isnull=False,
                ).values("user__profile__watched")
            )
        admin_user_ids = subscriptions.filter(
            scope=NotificationScope.SCOPE_ADMIN
        ).values("user_id")
        query |= models.Q(
            group__roles__permissions__codename="project.edit",
            group__memberships__limit_languages__isnull=True,
            group__memberships__user_id__in=admin_user_ids,
        )
        projects = Project.objects.filter(query).distinct()

    periodic_actions = tuple(notification.get_periodic_actions())
    if periodic_actions:
        changed_projects = Change.objects.filter(
            action__in=periodic_actions,
            timestamp__gte=since,
            timestamp__lt=until,
            project__isnull=False,
        ).values("project_id")
        projects = projects.filter(pk__in=changed_projects)
    return projects


@app.task(trail=False)
def notify_digest_batch(
    notification_name: str,
    frequency: int,
    since: str,
    until: str,
    user_ids: list[int] | None,
) -> None:
    """Generate one notification type for a recipient batch."""
    # ruff: ignore[import-outside-top-level]
    from weblate.accounts.notifications import (
        NOTIFICATIONS,
        NotificationFrequency,
    )

    outgoing: list[OutgoingEmail] = []
    notification_classes = {
        notification_cls.get_name(): notification_cls
        for notification_cls in NOTIFICATIONS
    }
    notification_cls = notification_classes[notification_name]
    parsed_since = datetime.fromisoformat(since)
    parsed_until = datetime.fromisoformat(until)
    parsed_frequency = NotificationFrequency(frequency)
    notification = notification_cls(outgoing, user_ids=user_ids)
    notification.notify_periodic_batch(
        parsed_frequency,
        since=parsed_since,
        until=parsed_until,
    )
    if outgoing:
        queue_mails(outgoing)


def notify_digest(method: str) -> None:
    from weblate.accounts.models import (  # ruff: ignore[import-outside-top-level]
        Subscription,
    )
    from weblate.accounts.notifications import (  # ruff: ignore[import-outside-top-level]
        DIGEST_USER_BATCH_SIZE,
        NOTIFICATIONS,
        NotificationFrequency,
    )

    periods = {
        "notify_daily": (NotificationFrequency.FREQ_DAILY, relativedelta(days=1)),
        "notify_weekly": (NotificationFrequency.FREQ_WEEKLY, relativedelta(weeks=1)),
        "notify_monthly": (
            NotificationFrequency.FREQ_MONTHLY,
            relativedelta(months=1),
        ),
    }
    frequency, period = periods[method]
    until = now()
    since = until - period
    since_value = since.isoformat()
    until_value = until.isoformat()

    for notification_cls in NOTIFICATIONS:
        subscriptions = Subscription.objects.filter(
            notification=notification_cls.get_name(),
            frequency=frequency,
            user__is_active=True,
            user__is_bot=False,
        )
        if not subscriptions.exists():
            continue

        if not notification_cls.batch_recipients:
            notify_digest_batch.delay(
                notification_cls.get_name(),
                frequency,
                since_value,
                until_value,
                None,
            )
            continue

        user_ids = (
            subscriptions.order_by("user_id")
            .values_list("user_id", flat=True)
            .distinct()
            .iterator(chunk_size=200)
        )
        for user_batch in batched(user_ids, DIGEST_USER_BATCH_SIZE):
            notify_digest_batch.delay(
                notification_cls.get_name(),
                frequency,
                since_value,
                until_value,
                list(user_batch),
            )


@app.task(trail=False)
def notify_daily() -> None:
    notify_digest("notify_daily")


@app.task(trail=False)
def notify_weekly() -> None:
    notify_digest("notify_weekly")


@app.task(trail=False)
def notify_monthly() -> None:
    notify_digest("notify_monthly")


@app.task(trail=False)
def notify_auditlog(log_id: int, email: str) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.accounts.models import (
        AuditLog,
    )

    # ruff: ignore[import-outside-top-level]
    from weblate.accounts.notifications import (
        send_notification_email,
    )

    audit = AuditLog.objects.get(pk=log_id)
    send_notification_email(
        audit.user.profile.language if audit.user else "en",
        [email],
        "account_activity",
        context={
            "message": audit.get_message,
            "extra_message": audit.get_extra_message,
            "address": audit.shortened_address,
            "user_agent": audit.user_agent,
            "password_reset_url": get_registration_attempt_password_reset_url(
                audit.activity
            ),
        },
        info=f"{audit.activity} from {audit.address}",
        user=audit.user,
    )


SMTP_DATA_PATCH = "_weblate_patched_data"


def weblate_logging_smtp_data(self: SMTP, msg: bytes) -> tuple[int, bytes]:
    (code, msg) = getattr(self, SMTP_DATA_PATCH)(msg)
    if code == 250:
        LOGGER.debug("SMTP completed (%s): %s", code, msg.decode())
    else:
        LOGGER.error("SMTP failed (%s): %s", code, msg.decode())
    return (code, msg)


def monkey_patch_smtp_logging(connection: BaseEmailBackend) -> BaseEmailBackend:
    if isinstance(connection, DjangoSMTPEmailBackend):
        # Ensure the connection is open
        connection.open()

        # Monkey patch smtplib.SMTP or smtplib.SMTP_SSL
        backend = connection.connection
        if isinstance(backend, SMTP) and not hasattr(backend, SMTP_DATA_PATCH):
            setattr(backend, SMTP_DATA_PATCH, backend.data)
            backend.data = MethodType(weblate_logging_smtp_data, backend)  # type: ignore[method-assign]

    return connection


def queue_mails(mails: list[OutgoingEmail]) -> None:
    """Enqueue e-mails for delivery in reasonable batches."""
    for offset in range(0, len(mails), EMAIL_BATCH_SIZE):
        send_mails.delay(mails[offset : offset + EMAIL_BATCH_SIZE])


@app.task(
    trail=False,
    autoretry_for=(SMTPConnectError, OSError),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def send_mails(mails: list[OutgoingEmail]) -> None:
    """Send multiple mails in single connection."""
    images = []
    with start_span(op="email.images"):
        for name in ("email-logo.png", "email-logo-footer.png"):
            image = MIMEPart()
            image.set_content(
                load_icon(name, auto_prefix=False),
                maintype="image",
                subtype="png",
                disposition="inline",
                filename=name,
                cid=f"<{name}@cid.weblate.org>",
            )
            images.append(image)

    with start_span(op="email.connect"):
        connection = get_connection()
        try:
            connection.open()
        except Exception:
            LOGGER.exception("Could not initialize e-mail backend")
            report_error("Could not send notifications")
            connection.close()
            return
        connection = monkey_patch_smtp_logging(connection)

    html2text = HTML2Text()

    with closing(connection):
        for mail in mails:
            with start_span(op="email.text"):
                text = html2text.handle(mail["body"])
            email = EmailMultiAlternatives(
                settings.EMAIL_SUBJECT_PREFIX + mail["subject"],
                text,
                to=[mail["address"]],
                headers=mail["headers"],
                connection=connection,
            )
            for image in images:
                email.attach(image)
            email.attach_alternative(mail["body"], "text/html")
            with start_span(op="email.send"):
                LOGGER.debug("sending e-mail to %s", mail["address"])
                email.send()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(3600, cleanup_social_auth.s(), name="social-auth-cleanup")
    sender.add_periodic_task(3600, cleanup_auditlog.s(), name="auditlog-cleanup")
    sender.add_periodic_task(
        3600, cleanup_totp_enrollments.s(), name="totp-enrollment-cleanup"
    )
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
