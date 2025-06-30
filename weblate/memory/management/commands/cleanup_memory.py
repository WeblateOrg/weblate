# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.memory.models import Memory
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for wiping out pending memories."""

    def handle(self, *args, **options) -> None:
        """Perform memory cleaning."""
        count, _ = Memory.objects.filter(status=Memory.STATUS_PENDING).delete()
        if count == 0:
            self.stdout.write("No pending memories found to clean.")
            return

        self.stdout.write(f"Cleaned {count} pending memories.")
