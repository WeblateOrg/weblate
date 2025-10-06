# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext

from weblate.accounts.notifications import send_notification_email
from weblate.billing.models import Billing, BillingEvent
from weblate.trans.tasks import project_removal
from weblate.utils.celery import app


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

    with_project = Billing.objects.annotate(Count("projects")).filter(
        projects__count__gt=0
    )
    toremove = with_project.exclude(removal=None).order_by("removal")
    trial = with_project.filter(removal=None, state=Billing.STATE_TRIAL).order_by(
        "expiry"
    )

    if limit or due or toremove or trial:
        send_notification_email(
            "en",
            [a[1] for a in settings.ADMINS] + settings.ADMINS_BILLING,
            "billing_check",
            context={
                "limit": limit,
                "due": due,
                "toremove": toremove,
                "trial": trial,
            },
        )


@app.task(trail=False)
def notify_expired() -> None:
    # Notify about expired billings
    possible_billings = Billing.objects.filter(
        # Active without payment (checked later)
        Q(state=Billing.STATE_ACTIVE)
        # Scheduled removal
        | Q(removal__isnull=False)
        # Trials expiring soon
        | Q(state=Billing.STATE_TRIAL, expiry__lte=timezone.now() + timedelta(days=7))
    ).exclude(projects__isnull=True)
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
                info=bill,
            )


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
            info=bill,
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
