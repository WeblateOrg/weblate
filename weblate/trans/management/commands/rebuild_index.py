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

from weblate.trans.management.commands import WeblateComponentCommand
from weblate.lang.models import Language
from weblate.trans.models import Unit
from weblate.trans.search import Fulltext
from weblate.trans.tasks import optimize_fulltext


class Command(WeblateComponentCommand):
    help = 'rebuilds index for fulltext search'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--clean',
            action='store_true',
            dest='clean',
            default=False,
            help='removes also all words from database'
        )
        parser.add_argument(
            '--optimize',
            action='store_true',
            dest='optimize',
            default=False,
            help='optimize index without rebuilding it'
        )

    def process_filtered(self, fulltext, **options):
        # Open writer
        source_writer = fulltext.get_source_index().writer()
        target_writers = {}

        try:
            # Process all units
            for unit in self.iterate_units(**options):
                lang = unit.translation.language.code
                # Lazy open writer
                if lang not in target_writers:
                    target_writers[lang] = fulltext.get_target_index(
                        lang
                    ).writer()
                # Update target index
                if unit.translation:
                    fulltext.update_target_unit_index(
                        target_writers[lang], unit
                    )
                # Update source index
                fulltext.update_source_unit_index(source_writer, unit)

        finally:
            # Close all writers
            source_writer.commit()
            for code in target_writers:
                target_writers[code].commit()

    def process_all(self, fulltext):
        source_writer = fulltext.get_source_index().writer()

        try:
            languages = Language.objects.have_translation()
            lang_count = len(languages)
            for index, language in enumerate(languages):
                self.stdout.write('Processing {} ({}/{})'.format(
                    language.code, index + 1, lang_count
                ))
                writer = fulltext.get_target_index(language.code).writer()
                try:
                    units = Unit.objects.filter(translation__language=language)
                    for unit in units.iterator():
                        if unit.translation:
                            fulltext.update_target_unit_index(writer, unit)
                        # Update source index
                        fulltext.update_source_unit_index(source_writer, unit)
                finally:
                    writer.commit()
        finally:
            source_writer.commit()

    def handle(self, *args, **options):
        # Optimize index
        if options['optimize']:
            optimize_fulltext()
            return
        fulltext = Fulltext()
        # Optionally rebuild indices from scratch
        if options['clean'] or options['all']:
            fulltext.cleanup()

        if options['all']:
            self.process_all(fulltext)
        else:
            self.process_filtered(fulltext, **options)
