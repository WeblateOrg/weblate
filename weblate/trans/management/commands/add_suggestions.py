# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from django.core.management.base import CommandError

from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.utils.management.base import WeblateTranslationCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(WeblateTranslationCommand):
    """Command for mass importing suggestions."""

    help = "imports suggestions"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--user", required=True, help="Username to record as the import actor"
        )
        parser.add_argument(
            "--author",
            default="noreply@weblate.org",
            help=("Email address of author (has to be registered in Weblate)"),
        )
        parser.add_argument("file", type=Path, help="File to import")

    def handle(self, *args, **options) -> None:
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist as error:
            msg = "User does not exist!"
            raise CommandError(msg) from error
        if user.is_anonymous:
            msg = "An anonymous user cannot import suggestions."
            raise CommandError(msg)

        # Get translation object
        translation = self.get_translation(**options)

        # Create fake request object
        request = AuthenticatedHttpRequest()
        request.user = user

        # Process import
        try:
            handle = options["file"].open("rb")
        except OSError as error:
            msg = f"Could not open file: {error}"
            raise CommandError(msg) from error
        with handle:
            try:
                translation.handle_upload(
                    request,
                    handle,
                    False,
                    method="suggest",
                    # Resolve authorship independently of the initiating actor,
                    # including the anonymous default suggestion author.
                    author=User.objects.get_author_by_email(
                        None, options["author"], None, request
                    ),
                )
            except OSError as error:
                msg = f"Could not import translation file: {error}"
                raise CommandError(msg) from error
