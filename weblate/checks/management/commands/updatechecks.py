# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.management.commands import WeblateLangCommand


class Command(WeblateLangCommand):
    help = "updates checks for units"

    def handle(self, *args, **options) -> None:
        translations = {}
        for unit in self.iterate_units(*args, **options):
            unit.run_checks()
            if unit.translation.id not in translations:
                translations[unit.translation.id] = unit.translation

        for translation in translations.values():
            translation.invalidate_cache()
