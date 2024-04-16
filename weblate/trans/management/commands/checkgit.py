# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "checks status of git repo"
    needs_repo = True

    def handle(self, *args, **options) -> None:
        """Show status of git repository in given projects."""
        for component in self.get_components(*args, **options):
            self.stdout.write(f"{component}:")
            self.stdout.write(component.repository.status())
