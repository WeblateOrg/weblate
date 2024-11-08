# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse

from django.core.management.base import CommandError
from django.http.request import HttpRequest

from weblate.trans.management.commands import WeblateTranslationCommand


class Command(WeblateTranslationCommand):
    """Command for mass importing suggestions."""

    help = "imports suggestions"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--author",
            default="noreply@weblate.org",
            help=("Email address of author (has to be registered in Weblate)"),
        )
        parser.add_argument("file", type=argparse.FileType("rb"), help="File to import")

    def handle(self, *args, **options) -> None:
        # Get translation object
        translation = self.get_translation(**options)

        # Create fake request object
        request = HttpRequest()
        request.user = None

        # Process import
        try:
            translation.handle_upload(
                request,
                options["file"],
                False,
                method="suggest",
                author_email=options["author"],
            )
        except OSError as error:
            msg = f"Could not import translation file: {error}"
            raise CommandError(msg) from error
        finally:
            options["file"].close()
