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
from weblate.trans.tasks import commit_pending


class Command(WeblateLangCommand):
    help = "commits pending changes older than given age"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--age",
            action="store",
            type=int,
            dest="age",
            default=None,
            help="Age of changes to commit in hours",
        )

    def handle(self, *args, **options):
        commit_pending(
            options["age"],
            set(self.get_translations(**options).values_list("id", flat=True)),
            self.stdout.write if int(options["verbosity"]) >= 1 else None,
        )
