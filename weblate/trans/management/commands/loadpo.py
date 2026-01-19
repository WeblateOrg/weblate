# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.trans.tasks import perform_load
from weblate.utils.management.base import WeblateLangCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(WeblateLangCommand):
    help = "(re)loads translations from disk"

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force rereading files even when they should be up to date",
        )
        parser.add_argument(
            "--foreground",
            action="store_true",
            default=False,
            help="Perform load in foreground (by default background task is used)",
        )

    def handle(self, *args, **options) -> None:
        langs = None
        if options["lang"] is not None:
            langs = options["lang"].split(",")
        loader = perform_load if options["foreground"] else perform_load.delay
        for component in self.get_components(**options):
            loader(component.pk, force=options["force"], langs=langs)
