# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.lang.models import Language
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Move all content from one language to other"

    def add_arguments(self, parser) -> None:
        parser.add_argument("source", help="Source language code")
        parser.add_argument("target", help="Target language code")

    def handle(self, *args, **options) -> None:
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

        source.change_set.update(language=target)

        source.component_set.update(source_language=target)
        for group in source.group_set.iterator():
            group.languages.remove(source)
            group.languages.add(target)

        for plural in source.plural_set.iterator():
            formulas = target.plural_set.filter(formula=plural.formula)
            try:
                new_plural = formulas[0]
            except IndexError:
                plural.language = target
                plural.save()
            else:
                plural.translation_set.update(plural=new_plural)
