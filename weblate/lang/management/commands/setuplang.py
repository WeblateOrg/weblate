# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

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
        Language.objects.setup(
            update=options["update"],
            logger=self.stdout.write if options["verbosity"] >= 1 else None,
        )
