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

from weblate.lang.models import Language
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Move all content from one language to other"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Actually delete the languages",
        )

    def handle(self, *args, **options):
        for language in Language.objects.filter(translation=None):
            if language.show_language_code:
                self.stdout.write(f"{language}: {language.translation_set.count()}")
                if options["delete"]:
                    language.delete()
