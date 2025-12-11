# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "forces committing changes to git repo"
    needs_repo = True

    def handle(self, *args, **options) -> None:
        """Commit pending translations in given projects."""
        for component in self.get_components(*args, **options):
            component.commit_pending("manage commitgit", None)
