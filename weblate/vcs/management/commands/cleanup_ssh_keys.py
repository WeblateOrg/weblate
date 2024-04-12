# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.utils.management.base import BaseCommand
from weblate.vcs.ssh import cleanup_host_keys


class Command(BaseCommand):
    help = "removes duplicate and invalid entries from SSH host keys"

    def handle(self, *args, **options) -> None:
        cleanup_host_keys(logger=self.stdout.write)
