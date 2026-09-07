# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.utils import timezone

from weblate.metrics.models import Metric
from weblate.utils.management.base import BaseCommand
from weblate.utils.stats import GlobalStats


class Command(BaseCommand):
    help = "ensures that stats are present"

    def handle(self, *args, **options) -> None:
        all_strings = GlobalStats().all
        self.stdout.write(f"found {all_strings} strings")
        today = timezone.now().date()
        if not Metric.objects.filter(date=today, scope=Metric.SCOPE_GLOBAL).exists():
            Metric.objects.collect_global(today)
