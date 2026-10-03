# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from asgiref.sync import async_to_sync
from django.core.management.base import CommandError

from weblate.utils.management.base import BaseCommand
from weblate.vcs.github import GitHubInstallation


class Command(BaseCommand):
    help = (
        "refreshes repositories of connected GitHub accounts and retargets "
        "components of renamed or transferred repositories"
    )

    def handle(self, *args: object, **options: object) -> None:
        failed = 0
        for installation in GitHubInstallation.objects.order_by("pk"):
            try:
                repositories = async_to_sync(installation.refresh_repositories)()
            except Exception as error:
                failed += 1
                self.stderr.write(
                    f"Failed to refresh {installation.hostname}/"
                    f"{installation.installation_id}: {error}"
                )
                continue
            self.stdout.write(
                f"Refreshed {len(repositories)} repositories for "
                f"{installation.hostname}/{installation.installation_id}"
            )
        if failed:
            msg = f"Failed to refresh {failed} connected GitHub accounts"
            raise CommandError(msg)
