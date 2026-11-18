# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from weblate.billing.models import Billing
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for billing check."""

    help = "extend pending approval billings"

    def handle(self, *args: object, **options: object) -> None:
        Billing.objects.filter(
            state=Billing.STATE_TRIAL, plan__price=0, libre_request_pending=True
        ).update(expiry=timezone.now() + timedelta(weeks=9), removal=None)
