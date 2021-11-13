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

from django.core.management.base import CommandError

from weblate.auth.models import User
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.trans.management.commands import WeblateTranslationCommand
from weblate.trans.models import Component
from weblate.trans.tasks import auto_translate


class Command(WeblateTranslationCommand):
    """Command for mass automatic translation."""

    help = "performs automatic translation based on other components"

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        # Get translation object
        translation = self.get_translation(**options)

        # Get user
        try:
            user = User.objects.get(username=options["user"])
        except User.DoesNotExist:
            raise CommandError("User does not exist!")

        source = None
        if options["source"]:
            parts = options["source"].split("/")
            if len(parts) != 2:
                raise CommandError("Invalid source component specified!")
            try:
                component = Component.objects.get(project__slug=parts[0], slug=parts[1])
            except Component.DoesNotExist:
                raise CommandError("No matching source component found!")
            source = component.id

        if options["mt"]:
            for translator in options["mt"]:
                if translator not in MACHINE_TRANSLATION_SERVICES.keys():
                    raise CommandError(
                        f"Machine translation {translator} is not available"
                    )

        if options["mode"] not in ("translate", "fuzzy", "suggest"):
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
