#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


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
