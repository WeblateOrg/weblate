# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse

from django.core.management.base import CommandError

from weblate.memory.models import Memory, MemoryImportError
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for importing translation memory."""

    help = "imports translation memory"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--language-map",
            help="Map language codes in the TMX to Weblate, for example en_US:en",
        )
        parser.add_argument(
            "file", type=argparse.FileType("rb"), help="File to import (TMX or JSON)"
        )

    def handle(self, *args, **options):
        """Translation memory import."""
        langmap = None
        if options["language_map"]:
            langmap = dict(z.split(":", 1) for z in options["language_map"].split(","))

        try:
            Memory.objects.import_file(None, options["file"], langmap)
        except MemoryImportError as error:
            raise CommandError(f"Import failed: {error}")
