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
from weblate.trans.search import Fulltext
from weblate.lang.models import Language
from weblate.memory.storage import TranslationMemory


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

    def optimize_index(self, fulltext):
        """Optimize index structures"""
        memory = TranslationMemory()
        memory.index.optimize()
        index = fulltext.get_source_index()
        index.optimize()
        languages = Language.objects.have_translation()
        for lang in languages:
            index = fulltext.get_target_index(lang.code)
            index.optimize()

    def handle(self, *args, **options):
        fulltext = Fulltext()
        # Optimize index
        if options['optimize']:
            self.optimize_index(fulltext)
            return
        # Optionally rebuild indices from scratch
        if options['clean']:
            fulltext.cleanup()

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
