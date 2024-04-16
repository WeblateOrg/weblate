# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.lang.models import Language
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Populates language definitions"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--no-update",
            action="store_false",
            dest="update",
            default=True,
            help="Prevents updates to existing language definitions",
        )

    def handle(self, *args, **options) -> None:
        """Create default set of languages."""
        kwargs = {}
        if options["verbosity"] >= 1:
            kwargs["logger"] = self.stdout.write
        Language.objects.setup(options["update"], **kwargs)
