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

from weblate.trans.management.commands import WeblateComponentCommand
from weblate.trans.tasks import perform_update


class Command(WeblateComponentCommand):
    help = "updates git repos"
    needs_repo = True

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--foreground",
            action="store_true",
            default=False,
            help="Perform load in foreground (by default backgroud task is used)",
        )

    def handle(self, *args, **options):
        if options["foreground"]:
            updater = perform_update
        else:
            updater = perform_update.delay
        for component in self.get_components(*args, **options):
            updater("Component", component.pk)
