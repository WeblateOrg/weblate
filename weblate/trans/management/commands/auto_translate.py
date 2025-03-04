# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.core.management.base import CommandError

from weblate.auth.models import User
from weblate.machinery.models import MACHINERY
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.management.commands import WeblateTranslationCommand
from weblate.trans.models import Component


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
            msg = "User does not exist!"
            raise CommandError(msg) from error

        source = None
        if options["source"]:
            try:
                component = Component.objects.get_by_path(options["source"])
            except Component.DoesNotExist as error:
                msg = "No matching source component found!"
                raise CommandError(msg) from error
            source = component.id

        if options["mt"]:
            for translator in options["mt"]:
                if translator not in MACHINERY:
                    msg = f"Machine translation {translator} is not available"
                    raise CommandError(msg)

        if options["mode"] not in {"translate", "fuzzy", "suggest"}:
            msg = "Invalid translation mode specified!"
            raise CommandError(msg)

        if options["inconsistent"]:
            filter_type = "check:inconsistent"
        elif options["overwrite"]:
            filter_type = "all"
        else:
            filter_type = "todo"

        auto = AutoTranslate(
            user=user,
            translation=translation,
            mode=options["mode"],
            filter_type=filter_type,
        )

        message = auto.perform(
            auto_source="mt" if options["mt"] else "others",
            source=source,
            engines=options["mt"],
            threshold=options["threshold"],
        )
        self.stdout.write(message)
