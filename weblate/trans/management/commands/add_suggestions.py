# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from django.core.management.base import CommandError
from django.http.request import HttpRequest

from weblate.trans.management.commands import WeblateTranslationCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(WeblateTranslationCommand):
    """Command for mass importing suggestions."""

    help = "imports suggestions"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--author",
            default="noreply@weblate.org",
            help=("Email address of author (has to be registered in Weblate)"),
        )
        parser.add_argument("file", type=Path, help="File to import")

    def handle(self, *args, **options) -> None:
        # Get translation object
        translation = self.get_translation(**options)

        # Create fake request object
        request = HttpRequest()
        request.user = None

        # Process import
        try:
            with options["file"].open("rb") as handle:
                try:
                    translation.handle_upload(
                        request,
                        handle,
                        False,
                        method="suggest",
                        author_email=options["author"],
                    )
                except OSError as error:
                    msg = f"Could not import translation file: {error}"
                    raise CommandError(msg) from error
        except OSError as error:
            msg = f"Could not open file: {error}"
            raise CommandError(msg) from error
