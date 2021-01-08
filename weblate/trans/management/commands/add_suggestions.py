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
from django.http.request import HttpRequest

from weblate.trans.management.commands import WeblateTranslationCommand


class Command(WeblateTranslationCommand):
    """Command for mass importing suggestions."""

    help = "imports suggestions"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--author",
            default="noreply@weblate.org",
            help=("Email address of author (has to be registered in Weblate)"),
        )
        parser.add_argument("file", type=argparse.FileType("rb"), help="File to import")

    def handle(self, *args, **options):
        # Get translation object
        translation = self.get_translation(**options)

        # Create fake request object
        request = HttpRequest()
        request.user = None

        # Process import
        try:
            translation.merge_upload(
                request,
                options["file"],
                False,
                method="suggest",
                author_email=options["author"],
            )
        except OSError as err:
            raise CommandError(f"Failed to import translation file: {err}")
        finally:
            options["file"].close()
