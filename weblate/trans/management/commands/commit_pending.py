# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.trans.management.commands import WeblateLangCommand
from weblate.trans.tasks import commit_pending


class Command(WeblateLangCommand):
    help = "commits pending changes older than given age"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--age",
            action="store",
            type=int,
            dest="age",
            default=None,
            help="Age of changes to commit in hours",
        )

    def handle(self, *args, **options) -> None:
        commit_pending(
            options["age"],
            set(self.get_translations(**options).values_list("id", flat=True)),
            self.stdout.write if int(options["verbosity"]) >= 1 else None,
        )
