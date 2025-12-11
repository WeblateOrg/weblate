# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

from django.utils.timezone import now

from weblate.billing.models import Billing, BillingEvent, Plan
from weblate.trans.models import Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for creating demo project."""

    help = "imports demo project and components"

    def handle(self, *args, **options) -> None:
        # Create project
        project = Project.objects.get_or_create(
            slug="billing-demo",
            defaults={"name": "Billing Demo", "web": "https://demo.weblate.org/"},
        )[0]

        # Create plans
        Plan.objects.get_or_create(
            slug="libre",
            defaults={
                "name": "Libre",
                "limit_projects": 1,
                "display_limit_projects": 1,
                "limit_hosted_strings": 160000,
                "display_limit_hosted_strings": 160000,
            },
        )
        plan = Plan.objects.get_or_create(
            slug="160k",
            defaults={
                "name": "160k strings",
                "limit_hosted_strings": 160000,
                "display_limit_hosted_strings": 160000,
            },
        )[0]

        # Create billing
        try:
            billing = project.billing_set.get()
        except Billing.DoesNotExist:
            billing = Billing.objects.create(plan=plan)
            billing.projects.add(project)

        # Add invoice
        start = now()
        try:
            invoice = billing.get_last_invoice_object()
        except IndexError:
            pass
        else:
            start = invoice.end + timedelta(days=1)
        billing.invoice_set.create(
            amount=1, start=start, end=start + timedelta(days=31)
        )

        # Add event
        billing.billinglog_set.create(event=BillingEvent.EMAIL, summary="Imported demo")
