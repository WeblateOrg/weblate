# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from celery.schedules import crontab

from django.urls import reverse

from weblate.accounts.notifications import send_notification_email
from weblate.auth.models import User
from weblate.celery import app
from weblate.billing.models import Billing
from weblate.utils.site import get_site_url


@app.task
def billing_check():
    Billing.objects.check_limits()


@app.task
def billing_alert():
    for bill in Billing.objects.filter(state=Billing.STATE_ACTIVE):
        in_limit = bill.in_display_limits()
        for project in bill.projects.all():
            for component in project.component_set.all():
                if in_limit:
                    component.delete_alert('BillingLimit')
                else:
                    component.add_alert('BillingLimit')


@app.task
def billing_notify():
    billing_check()

    limit = Billing.objects.get_out_of_limits()
    due = Billing.objects.get_unpaid()

    if limit or due:
        send_notification_email(
            'en', 'ADMINS', 'billing_check',
            context={'limit': limit, 'due': due}
        )


@app.task
def notify_expired():
    for bill in Billing.objects.filter(state=Billing.STATE_ACTIVE):
        if bill.check_payment_status():
            continue
        users = bill.owners.distinct()
        for project in bill.projects.all():
            users |= User.objects.having_perm('billing.view', project)

        for user in users:
            send_notification_email(
                user.profile.language,
                user.email,
                'billing_expired',
                context={
                    'billing': bill,
                    'billing_url': get_site_url(reverse('billing')),
                },
                info=bill,
            )


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        3600,
        billing_check.s(),
        name='billing-check',
    )
    sender.add_periodic_task(
        3600 * 24,
        billing_alert.s(),
        name='billing-alert',
    )
    sender.add_periodic_task(
        3600 * 24,
        billing_notify.s(),
        name='billing-notify',
    )
    sender.add_periodic_task(
        crontab(hour=2, minute=30, day_of_week='monday,thursday'),
        notify_expired.s(),
        name='notify-expired',
    )
