# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.db.models import Q

from weblate.memory.models import Memory
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    """Command for exporting translation memory."""

    help = "exports translation memory in JSON format"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--indent",
            default=2,
            dest="indent",
            type=int,
            help=("Specifies the indent level to use when pretty-printing output."),
        )
        parser.add_argument(
            "--backup",
            action="store_true",
            help="Store backup to the backups directory in the DATA_DIR",
        )

    def handle(self, *args, **options) -> None:
        memory = Memory.objects.filter_scope(Q()).prefetch_scopes().prefetch_lang()
        self.stdout.ending = None  # type: ignore[assignment]
        json.dump(
            [entry for item in memory for entry in item.as_dicts()],
            self.stdout,
            indent=options["indent"],
        )
        self.stdout.write("\n")
