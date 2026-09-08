# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.utils.celery import get_queue_stats
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "display Celery queue status"

    def handle(self, *args: object, **options: object) -> None:
        for key, value in sorted(get_queue_stats().items()):
            self.stdout.write(f"{key}: {value}")
