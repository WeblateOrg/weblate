# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.core.management.base import BaseCommand

from weblate.lang.models import Language, Plural


class Command(BaseCommand):
    help = 'Move all content from one language to other'

    def add_arguments(self, parser):
        parser.add_argument(
            'source',
            help='Source language code'
        )
        parser.add_argument(
            'target',
            help='Target language code'
        )

    def handle(self, *args, **options):
        source = Language.objects.get(code=options['source'])
        target = Language.objects.get(code=options['target'])

        source.suggestion_set.update(language=target)
        source.translation_set.update(language=target)
        source.whiteboardmessage_set.update(language=target)

        for profile in source.profile_set.all():
            profile.languages.remove(source)
            profile.languages.add(target)

        for profile in source.secondary_profile_set.all():
            profile.secondary_languages.remove(source)
            profile.secondary_languages.add(target)

        source.project_set.update(source_language=target)
        for group in source.group_set.all():
            group.languages.remove(source)
            group.languages.add(target)
        source.dictionary_set.update(language=target)
        source.comment_set.update(language=target)
        source.check_set.update(language=target)

        for plural in source.plural_set.all():
            try:
                new_plural = target.plural_set.get(
                    equation=plural.equation,
                )
                plural.translation_set.update(plural=new_plural)
            except Plural.DoesNotExist:
                plural.language = target
                plural.save()
