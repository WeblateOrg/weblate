# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta

from django.utils import timezone

from weblate.billing.models import Billing
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for billing check."""

    help = "extend pending approval billings"

    def handle(self, *args, **options) -> None:
        pending = [
            bill
            for bill in Billing.objects.filter(state=Billing.STATE_TRIAL)
            if bill.payment.get("libre_request")
        ]
        for bill in pending:
            bill.expiry = timezone.now() + timedelta(days=9 * 7)
            bill.removal = None
        Billing.objects.bulk_update(pending, ["expiry", "removal"])
