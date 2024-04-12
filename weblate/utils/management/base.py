# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand as DjangoBaseCommand


class BaseCommand(DjangoBaseCommand):
    requires_system_checks = []

    def execute(self, *args, **options):
        logger = logging.getLogger("weblate")
        if not any(handler.get_name() == "console" for handler in logger.handlers):
            console = logging.StreamHandler()
            console.set_name("console")
            verbosity = int(options["verbosity"])
            if verbosity > 1:
                console.setLevel(logging.DEBUG)
            elif verbosity == 1:
                console.setLevel(logging.INFO)
            else:
                console.setLevel(logging.ERROR)
            console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(console)
        return super().execute(*args, **options)

    def handle(self, *args, **options) -> None:
        raise NotImplementedError
