# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.billing.models import Billing
from weblate.billing.tasks import billing_notify
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for billing check."""

    help = "checks billing limits"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--valid", action="store_true", help="list valid ones")
        parser.add_argument(
            "--notify", action="store_true", help="send email notifications"
        )

    def handle(self, *args, **options) -> None:
        if options["notify"]:
            billing_notify()
            return
        Billing.objects.check_limits()
        if options["valid"]:
            for bill in Billing.objects.get_valid():
                self.stdout.write(f" * {bill}")
            return
        limit = Billing.objects.get_out_of_limits()
        due = Billing.objects.get_unpaid()

        if limit:
            self.stdout.write("Following billings are over limit:")
            for bill in limit:
                self.stdout.write(f" * {bill}")

        if due:
            self.stdout.write("Following billings are past due date:")
            for bill in due:
                self.stdout.write(f" * {bill}")
