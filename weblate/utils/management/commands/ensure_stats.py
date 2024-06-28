# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.utils import timezone

from weblate.metrics.models import Metric
from weblate.metrics.tasks import collect_metrics
from weblate.utils.management.base import BaseCommand
from weblate.utils.stats import GlobalStats


class Command(BaseCommand):
    help = "ensures that stats are present"

    def handle(self, *args, **options) -> None:
        all_strings = GlobalStats().all
        self.stdout.write(f"found {all_strings} strings")
        if not Metric.objects.filter(
            date=timezone.now().date(), scope=Metric.SCOPE_GLOBAL
        ).exists():
            collect_metrics()
