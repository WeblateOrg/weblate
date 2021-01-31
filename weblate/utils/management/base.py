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

    def handle(self, *args, **options):
        """The actual logic of the command.

        Subclasses must implement this method.
        """
        raise NotImplementedError()
