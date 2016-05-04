# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from weblate.trans.management.commands import WeblateCommand
from weblate.trans.search import (
    get_source_index, get_target_index,
    update_source_unit_index, update_target_unit_index,
    clean_indexes,
)
from weblate.lang.models import Language


class Command(WeblateCommand):
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

    def optimize_index(self):
        """Optimizes index structures"""
        index = get_source_index()
        index.optimize()
        languages = Language.objects.have_translation()
        for lang in languages:
            index = get_target_index(lang.code)
            index.optimize()

    def handle(self, *args, **options):
        # Optimize index
        if options['optimize']:
            self.optimize_index()
            return
        # Optionally rebuild indices from scratch
        if options['clean']:
            clean_indexes()

        # Open writer
        source_writer = get_source_index().writer()
        target_writers = {}

        try:
            # Process all units
            for unit in self.iterate_units(**options):
                lang = unit.translation.language.code
                # Lazy open writer
                if lang not in target_writers:
                    target_writers[lang] = get_target_index(lang).writer()
                # Update target index
                if unit.translation:
                    update_target_unit_index(target_writers[lang], unit)
                # Update source index
                update_source_unit_index(source_writer, unit)

        finally:
            # Close all writers
            source_writer.commit()
            for code in target_writers:
                target_writers[code].commit()
