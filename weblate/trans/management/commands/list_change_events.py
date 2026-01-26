# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from weblate.trans.actions import ActionEvents
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List change events"

    def handle(self, *args, **options):
        """List change events."""
        self.stdout.write(""".. list-table:: Available choices:
   :width: 100%

""")

        for event in ActionEvents:
            self.stdout.write(f"   * - ``{event.value}``\n     - {event.label}\n")
