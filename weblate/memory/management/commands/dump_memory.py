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

import json

from weblate.memory.models import Memory
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for exporting translation memory."""

    help = "exports translation memory in JSON format"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--indent",
            default=2,
            dest="indent",
            type=int,
            help=("Specifies the indent level to use when " "pretty-printing output."),
        )
        parser.add_argument(
            "--backup",
            action="store_true",
            help="Store backup to the backups directory in the DATA_DIR",
        )

    def handle(self, *args, **options):
        memory = Memory.objects.all().prefetch_lang()
        self.stdout.ending = None
        json.dump(
            [item.as_dict() for item in memory], self.stdout, indent=options["indent"]
        )
        self.stdout.write("\n")
