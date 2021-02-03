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

from weblate.lang.models import Language, Plural
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Move all content from one language to other"

    def add_arguments(self, parser):
        parser.add_argument("source", help="Source language code")
        parser.add_argument("target", help="Target language code")

    def handle(self, *args, **options):
        source = Language.objects.get(code=options["source"])
        target = Language.objects.get(code=options["target"])

        for translation in source.translation_set.iterator():
            other = translation.component.translation_set.filter(language=target)
            if other.exists():
                self.stderr.write(f"Already exists: {translation}")
                continue
            translation.language = target
            translation.save()
        source.announcement_set.update(language=target)

        for profile in source.profile_set.iterator():
            profile.languages.remove(source)
            profile.languages.add(target)

        for profile in source.secondary_profile_set.iterator():
            profile.secondary_languages.remove(source)
            profile.secondary_languages.add(target)

        source.component_set.update(source_language=target)
        for group in source.group_set.iterator():
            group.languages.remove(source)
            group.languages.add(target)

        for plural in source.plural_set.iterator():
            try:
                new_plural = target.plural_set.get(formula=plural.formula)
                plural.translation_set.update(plural=new_plural)
            except Plural.DoesNotExist:
                plural.language = target
                plural.save()
