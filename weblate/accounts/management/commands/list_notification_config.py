# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.accounts.notifications import (
    NOTIFICATIONS,
    NotificationFrequency,
    NotificationScope,
)
from weblate.utils.management.base import DocGeneratorCommand

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.accounts.notifications import (
        Notification,
    )


def sorted_handlers(
    handlers: Iterable[type[Notification]],
) -> Iterable[type[Notification]]:
    return sorted(handlers, key=lambda handler: handler.__name__)


class Command(DocGeneratorCommand):
    help = "Lists notification scopes, frequencies and handlers"

    def handle(self, *args, **options) -> None:
        """List notification scopes, frequencies and handlers."""
        scope_content = []
        for scope in NotificationScope:
            scope_content.extend(
                [f"``{scope.value}``", f"   :guilabel:`{scope.label}`"]
            )
        self.add_section("notification-scopes", scope_content)

        frequency_content = []
        for frequency in NotificationFrequency:
            frequency_content.extend(
                [f"``{frequency.value}``", f"   :guilabel:`{frequency.label}`"]
            )
        self.add_section("notification-frequencies", frequency_content)

        handler_content = []
        for handler in sorted_handlers(NOTIFICATIONS):
            handler_content.extend(
                [f"``{handler.__name__}``", f"   :guilabel:`{handler.verbose}`"]
            )
        self.add_section("notification-handlers", handler_content)

        self.write_sections(options.get("output"))
