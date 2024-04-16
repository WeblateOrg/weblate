# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.management.commands import WeblateComponentCommand
from weblate.trans.tasks import perform_update


class Command(WeblateComponentCommand):
    help = "updates git repos"
    needs_repo = True

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--foreground",
            action="store_true",
            default=False,
            help="Perform load in foreground (by default background task is used)",
        )

    def handle(self, *args, **options) -> None:
        updater = perform_update if options["foreground"] else perform_update.delay
        for component in self.get_components(*args, **options):
            updater("Component", component.pk)
