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

from weblate.trans.management.commands import WeblateLangCommand
from weblate.trans.tasks import perform_load


class Command(WeblateLangCommand):
    help = "(re)loads translations from disk"

    def add_arguments(self, parser):
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
            help="Perform load in foreground (by default backgroud task is used)",
        )

    def handle(self, *args, **options):
        langs = None
        if options["lang"] is not None:
            langs = options["lang"].split(",")
        if options["foreground"]:
            loader = perform_load
        else:
            loader = perform_load.delay
        for component in self.get_components(**options):
            loader(component.pk, force=options["force"], langs=langs)
