# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext

from weblate.accounts.notifications import send_notification_email
from weblate.billing.models import Billing, BillingEvent
from weblate.trans.tasks import project_removal
from weblate.utils.celery import app

if TYPE_CHECKING:
    from datetime import datetime


@app.task(trail=False)
def billing_check(billing_id: int | None = None) -> None:
    if billing_id is None:
        Billing.objects.check_limits()
    else:
        Billing.objects.get(pk=billing_id).check_limits()


@app.task(trail=False)
def billing_notify() -> None:
    billing_check()

    limit = Billing.objects.get_out_of_limits()
    due = Billing.objects.get_unpaid()
    inactive_recurring = list(
        Billing.objects.filter(state=Billing.STATE_ACTIVE)
        .filter(payment__has_key="recurring")
        .filter(inactive_recurring_disable__isnull=False)
        .prefetch()
    )

    billing_projects = Billing.projects.through.objects.filter(
        billing_id=OuterRef("pk")
    )
    with_project = Billing.objects.alias(has_projects=Exists(billing_projects)).filter(
        has_projects=True
    )
    toremove = with_project.exclude(removal=None).order_by("removal")
    trial = with_project.filter(removal=None, state=Billing.STATE_TRIAL).order_by(
        "expiry"
    )

    if limit or due or toremove or trial or inactive_recurring:
        send_notification_email(
            "en",
            [*settings.ADMINS, *settings.ADMINS_BILLING],
            "billing_check",
            context={
                "limit": limit,
                "due": due,
                "toremove": toremove,
                "trial": trial,
                "inactive_recurring": inactive_recurring,
            },
        )


@app.task(trail=False)
def notify_expired() -> None:
    # Notify about expired billings
    billing_projects = Billing.projects.through.objects.filter(
        billing_id=OuterRef("pk")
    )
    possible_billings = Billing.objects.alias(
        has_projects=Exists(billing_projects)
    ).filter(
        # Active without payment (checked later)
        Q(state=Billing.STATE_ACTIVE)
        # Scheduled removal
        | Q(removal__isnull=False)
        # Trials expiring soon
        | Q(state=Billing.STATE_TRIAL, expiry__lte=timezone.now() + timedelta(days=7)),
        has_projects=True,
    )
    for bill in possible_billings:
        if bill.state == Billing.STATE_ACTIVE and bill.check_payment_status(now=True):
            continue
        if bill.plan.price:
            note = gettext(
                "You will stop receiving this notification once "
                "you pay the bills or the project is removed."
            )
        else:
            note = gettext(
                "You will stop receiving this notification once "
                "you change to regular subscription or the project is removed."
            )

        for user in bill.get_notify_users():
            bill.billinglog_set.create(
                event=BillingEvent.EMAIL, summary="Billing expired", user=user
            )
            send_notification_email(
                user.profile.language,
                [user.email],
                "billing_expired",
                context={
                    "billing": bill,
                    "payment_enabled": getattr(settings, "PAYMENT_ENABLED", False),
                    "unsubscribe_note": note,
                },
                info=str(bill),
                user=user,
            )


def notify_inactive_recurring(bill: Billing, status: dict[str, datetime]) -> None:
    planned_disable = status["planned_disable"]
    for user in bill.get_notify_users():
        bill.billinglog_set.create(
            event=BillingEvent.EMAIL,
            summary="Inactive recurring payment warning",
            user=user,
            details=Billing.serialize_inactive_recurring_status(status),
        )
        send_notification_email(
            user.profile.language,
            [user.email],
            "billing_inactive_recurring",
            context={
                "billing": bill,
                "planned_disable": planned_disable,
                **status,
                "payment_enabled": getattr(settings, "PAYMENT_ENABLED", False),
            },
            info=str(bill),
            user=user,
        )


@app.task(trail=False)
def inactive_recurring_check() -> None:
    now = timezone.now()
    for billing_id in (
        Billing.objects.filter(
            Q(
                state=Billing.STATE_ACTIVE,
                payment__has_key="recurring",
                plan__yearly_price__gt=0,
            )
            | Q(inactive_recurring_notification__isnull=False)
            | Q(inactive_recurring_latest_commit__isnull=False)
            | Q(inactive_recurring_oldest_pending_change__isnull=False)
            | Q(inactive_recurring_repository_changes__isnull=False)
            | Q(inactive_recurring_push_failure__isnull=False)
            | Q(inactive_recurring_disable__isnull=False)
        )
        .values_list("pk", flat=True)
        .distinct()
    ):
        with transaction.atomic():
            bill = (
                Billing.objects.select_for_update()
                .select_related("plan")
                .prefetch_related("owners", "owners__profile", "projects")
                .get(pk=billing_id)
            )
            status = bill.get_inactive_recurring_status(now)
            if status is None:
                bill.clear_inactive_recurring_status()
                continue

            planned_disable = status["planned_disable"]
            if planned_disable <= now:
                bill.disable_inactive_recurring(status)
                continue

            if bill.inactive_recurring_notification is not None:
                continue

            bill.mark_inactive_recurring(status, now=now)
            notify_inactive_recurring(bill, status)


@app.task(trail=False)
@transaction.atomic
def schedule_removal() -> None:
    removal = timezone.now() + timedelta(days=settings.BILLING_REMOVAL_PERIOD)
    for bill in Billing.objects.filter(
        state=Billing.STATE_ACTIVE, removal=None
    ).select_for_update():
        if bill.check_payment_status():
            continue
        bill.billinglog_set.create(
            event=BillingEvent.UNPAID,
            summary=f"Scheduled removal at {removal.isoformat()}",
        )
        bill.removal = removal
        bill.save(update_fields=["removal"])


@app.task(trail=False)
@transaction.atomic
def remove_single_billing(billing_id: int) -> None:
    bill = Billing.objects.select_for_update().get(pk=billing_id)
    for user in bill.get_notify_users():
        bill.billinglog_set.create(
            event=BillingEvent.EMAIL, summary="Billing removed", user=user
        )
        send_notification_email(
            user.profile.language,
            [user.email],
            "billing_expired",
            context={"billing": bill, "final_removal": True},
            info=str(bill),
            user=user,
        )
    for prj in bill.projects.iterator():
        bill.billinglog_set.create(
            event=BillingEvent.REMOVED, summary=f"Removed project {prj}"
        )
        prj.log_warning("removing due to unpaid billing")
        project_removal(prj.id, None)
    bill.removal = None
    bill.state = Billing.STATE_TERMINATED
    bill.save()
    bill.billinglog_set.create(event=BillingEvent.REMOVED, summary="Terminated billing")


@app.task(trail=False)
def perform_removal() -> None:
    for bill in Billing.objects.filter(removal__lte=timezone.now()).iterator():
        remove_single_billing.delay(bill.pk)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    sender.add_periodic_task(3600, billing_check.s(), name="billing-check")
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day_of_week="mon,thu"),
        billing_notify.s(),
        name="billing-notify",
    )
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        perform_removal.s(),
        name="perform-removal",
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week="mon,thu"),
        schedule_removal.s(),
        name="schedule-removal",
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week="mon,thu"),
        notify_expired.s(),
        name="notify-expired",
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=45),
        inactive_recurring_check.s(),
        name="inactive-recurring-check",
    )
