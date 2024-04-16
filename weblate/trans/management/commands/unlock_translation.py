# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "unlocks component for editing"

    def handle(self, *args, **options) -> None:
        for component in self.get_components(*args, **options):
            if component.locked:
                component.do_lock(None, False)
