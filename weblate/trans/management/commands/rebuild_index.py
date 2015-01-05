# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
from weblate.lang.models import Language
from weblate.trans.search import (
    create_source_index, create_target_index,
    get_source_index, get_target_index,
    update_source_unit_index, update_target_unit_index,
)
from optparse import make_option


class Command(WeblateCommand):
    help = 'rebuilds index for fulltext search'
    option_list = WeblateCommand.option_list + (
        make_option(
            '--clean',
            action='store_true',
            dest='clean',
            default=False,
            help='removes also all words from database'
        ),
    )

    def handle(self, *args, **options):
        # Optionally rebuild indices from scratch
        if options['clean']:
            create_source_index()
            for lang in Language.objects.have_translation():
                create_target_index(lang=lang.code)

        # Open writer
        source_writer = get_source_index().writer()
        target_writers = {}

        try:
            # Process all units
            for unit in self.iterate_units(*args, **options):
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
            for lang in target_writers:
                target_writers[lang].commit()
