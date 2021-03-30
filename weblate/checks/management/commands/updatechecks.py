#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from weblate.trans.management.commands import WeblateLangCommand


class Command(WeblateLangCommand):
    help = "updates checks for units"

    def handle(self, *args, **options):
        translations = {}
        for unit in self.iterate_units(*args, **options):
            unit.run_checks()
            if unit.translation.id not in translations:
                translations[unit.translation.id] = unit.translation

        for translation in translations.values():
            translation.invalidate_cache()
