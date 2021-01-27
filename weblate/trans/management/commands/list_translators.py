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


class Command(WeblateComponentCommand):
    help = "List translators for a component"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--language-code",
            action="store_true",
            dest="code",
            default=False,
            help="Use language code instead of language name",
        )

    def handle(self, *args, **options):
        data = []
        for component in self.get_components(*args, **options):
            for translation in component.translation_set.iterator():
                authors = translation.change_set.authors_list()
                if not authors:
                    continue
                if options["code"]:
                    key = translation.language.code
                else:
                    key = translation.language.name
                data.append({key: sorted(set(authors))})
        for language in data:
            name, translators = language.popitem()
            self.stdout.write(f"[{name}]\n")
            for translator in translators:
                self.stdout.write("{1} <{0}>\n".format(*translator))
