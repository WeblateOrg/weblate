# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.auth.bots import InternalBot
from weblate.trans.recovery import checkout_needs_recovery
from weblate.trans.repository import (
    RepositoryOperationConflictError,
    queue_repository_operation,
)
from weblate.utils.management.base import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "queues reset and reapply for components with missing Git checkout"
    needs_repo = True

    def handle(self, *args: object, **options: object) -> None:
        user = InternalBot.REPOSITORY.get_user()
        for component in self.get_components(**options).prefetch():
            if not checkout_needs_recovery(component.repository):
                continue
            try:
                queue_repository_operation(component, "reset-keep", user)
            except RepositoryOperationConflictError:
                self.stderr.write(
                    f"{component.full_slug}: another repository operation is in progress"
                )
            else:
                self.stdout.write(f"{component.full_slug}: queued recovery")
