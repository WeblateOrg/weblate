# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.trans.actions import ActionEvents, get_change_action_identifier
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List change events"

    def handle(self, *args, **options) -> None:
        """List change events."""
        self.stdout.write(
            """.. list-table:: Available choices:
   :width: 100%
   :header-rows: 1

   * - ID
     - Identifier
     - Name
     - Description
"""
        )
        for event in ActionEvents:
            self.stdout.write(
                f"   * - ``{event.value}``\n"
                f"     - ``{get_change_action_identifier(event.label)}``\n"
                f"     - {event.label}\n"
                f"     - {event.description}\n"
            )
