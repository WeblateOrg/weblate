# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.management.base import CommandError

from weblate.auth.models import User
from weblate.machinery.models import MACHINERY
from weblate.trans.management.commands import WeblateTranslationCommand
from weblate.trans.models import Component
from weblate.trans.tasks import auto_translate


class Command(WeblateTranslationCommand):
    """Command for mass automatic translation."""

    help = "performs automatic translation based on other components"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--user", default="anonymous", help=("User performing the change")
        )
        parser.add_argument(
            "--source", default="", help=("Source component <project/component>")
        )
        parser.add_argument(
            "--add",
            default=False,
            action="store_true",
            help=("Add translations if they do not exist"),
        )
        parser.add_argument(
            "--overwrite",
            default=False,
            action="store_true",
            help=("Overwrite existing translations in target component"),
        )
        parser.add_argument(
            "--inconsistent",
            default=False,
            action="store_true",
            help=("Process only inconsistent translations"),
        )
        parser.add_argument(
            "--mt", action="append", default=[], help=("Add machine translation source")
        )
        parser.add_argument(
            "--threshold",
            default=80,
            type=int,
            help=("Set machine translation threshold"),
        )
        parser.add_argument(
            "--mode",
            default="translate",
            help=("Translation mode; translate, fuzzy or suggest"),
        )

    def handle(self, *args, **options) -> None:
        # Get translation object
        translation = self.get_translation(**options)

        # Get user
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist as error:
            raise CommandError("User does not exist!") from error

        source = None
        if options["source"]:
            try:
                component = Component.objects.get_by_path(options["source"])
            except Component.DoesNotExist as error:
                raise CommandError("No matching source component found!") from error
            source = component.id

        if options["mt"]:
            for translator in options["mt"]:
                if translator not in MACHINERY:
                    raise CommandError(
                        f"Machine translation {translator} is not available"
                    )

        if options["mode"] not in {"translate", "fuzzy", "suggest"}:
            raise CommandError("Invalid translation mode specified!")

        if options["inconsistent"]:
            filter_type = "check:inconsistent"
        elif options["overwrite"]:
            filter_type = "all"
        else:
            filter_type = "todo"

        result = auto_translate(
            user.id,
            translation.id,
            options["mode"],
            filter_type,
            "mt" if options["mt"] else "others",
            source,
            options["mt"],
            options["threshold"],
            translation=translation,
        )
        self.stdout.write(result["message"])
