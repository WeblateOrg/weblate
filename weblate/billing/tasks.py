#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from datetime import timedelta

from celery.schedules import crontab
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from weblate.accounts.notifications import send_notification_email
from weblate.billing.models import Billing
from weblate.utils.celery import app


@app.task(trail=False)
def billing_check():
    Billing.objects.check_limits()


@app.task(trail=False)
def billing_alert():
    for bill in Billing.objects.filter(state=Billing.STATE_ACTIVE):
        in_limit = bill.in_display_limits()
        for project in bill.projects.iterator():
            for component in project.component_set.iterator():
                if in_limit:
                    component.delete_alert("BillingLimit")
                else:
                    component.add_alert("BillingLimit")


@app.task(trail=False)
def billing_notify():
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
def notify_expired():
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
            note = _(
                "You will stop receiving this notification once "
                "you pay the bills or the project is removed."
            )
        else:
            note = _(
                "You will stop receiving this notification once "
                "you change to regular subscription or the project is removed."
            )

        for user in bill.get_notify_users():
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
def schedule_removal():
    removal = timezone.now() + timedelta(days=settings.BILLING_REMOVAL_PERIOD)
    for bill in Billing.objects.filter(state=Billing.STATE_ACTIVE, removal=None):
        if bill.check_payment_status():
            continue
        bill.removal = removal
        bill.save(update_fields=["removal"])


@app.task(trail=False)
def perform_removal():
    for bill in Billing.objects.filter(removal__lte=timezone.now()):
        for user in bill.get_notify_users():
            send_notification_email(
                user.profile.language,
                [user.email],
                "billing_expired",
                context={"billing": bill, "final_removal": True},
                info=bill,
            )
        for prj in bill.projects.iterator():
            prj.log_warning("removing due to unpaid billing")
            prj.stats.invalidate()
            prj.delete()
        bill.removal = None
        bill.state = Billing.STATE_TERMINATED
        bill.save()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600, billing_check.s(), name="billing-check")
    sender.add_periodic_task(3600 * 24, billing_alert.s(), name="billing-alert")
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day_of_week="monday,thursday"),
        billing_notify.s(),
        name="billing-notify",
    )
    sender.add_periodic_task(
        crontab(hour=1, minute=0),
        perform_removal.s(),
        name="perform-removal",
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=0, day_of_week="monday,thursday"),
        schedule_removal.s(),
        name="schedule-removal",
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week="monday,thursday"),
        notify_expired.s(),
        name="notify-expired",
    )
