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

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from weblate.billing.models import Billing


class Command(BaseCommand):
    """Command for billing check."""
    help = 'checks billing limits'

    def add_arguments(self, parser):
        parser.add_argument(
            '--grace',
            type=int,
            default=30,
            help='grace period'
        )

    def handle(self, *args, **options):
        header = False
        for bill in Billing.objects.all():
            if not bill.in_limits():
                if not header:
                    self.stdout.write('Following billings are over limit:')
                    header = True
                self.stdout.write(
                    ' * {0}'.format(bill)
                )
        header = False
        due_date = timezone.now() - timedelta(days=options['grace'])
        for bill in Billing.objects.filter(state=Billing.STATE_ACTIVE):
            if not bill.invoice_set.filter(end__gt=due_date).exists():
                if not header:
                    self.stdout.write('Following billings are past due date:')
                    header = True
                self.stdout.write(
                    ' * {0}'.format(bill)
                )
