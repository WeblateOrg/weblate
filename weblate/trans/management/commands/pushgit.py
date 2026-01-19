# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.utils.management.base import WeblateComponentCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(WeblateComponentCommand):
    help = "pushes all changes to upstream repository"
    needs_repo = True

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--force-commit",
            action="store_true",
            dest="force_commit",
            default=False,
            help="Forces committing pending changes",
        )

    def handle(self, *args, **options) -> None:
        for component in self.get_components(**options):
            component.do_push(None, force_commit=options["force_commit"])
