# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.management.base import BaseCommand
from django.db.models import Count

from weblate.checks.models import Check


class Command(BaseCommand):
    help = "lists top untranslated failing checks"

    def handle(self, *args, **options) -> None:
        results = (
            Check.objects.filter(name="same")
            .values("unit__source")
            .annotate(Count("unit__source"))
            .filter(unit__source__count__gt=1)
            .order_by("-unit__source__count")
        )

        for item in results:
            self.stdout.write(
                "{:5d} {}".format(item["unit__source__count"], item["unit__source"])
            )
