# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Drop in Weblate 4.17

from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "deprecated, will be removed in Weblate 4.17"

    def handle(self, *args, **options):
        self.stderr.write(
            "This command does nothing, it will be removed in Weblate 4.17!"
        )
