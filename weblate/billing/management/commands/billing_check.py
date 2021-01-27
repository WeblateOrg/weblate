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


from weblate.billing.models import Billing
from weblate.billing.tasks import billing_notify
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for billing check."""

    help = "checks billing limits"

    def add_arguments(self, parser):
        parser.add_argument("--valid", action="store_true", help="list valid ones")
        parser.add_argument(
            "--notify", action="store_true", help="send email notifications"
        )

    def handle(self, *args, **options):
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
