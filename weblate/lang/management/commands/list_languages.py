# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import activate, gettext

from weblate.lang.models import Language
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "List language definitions"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--lower", action="store_true", help="Lowercase translated name"
        )
        parser.add_argument("locale", help="Locale for printing")

    def handle(self, *args, **options) -> None:
        """
        Create default set of languages.

        Optionally updating them to match current shipped definitions.
        """
        activate(options["locale"])
        for language in Language.objects.order():
            name = gettext(language.name)
            if options["lower"]:
                name = name[0].lower() + name[1:]
            self.stdout.write(f"| {language.code} || {language.name} || {name}")
            self.stdout.write("|-")
