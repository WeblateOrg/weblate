# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from lang.models import Language
from weblate.trans.search import update_index, create_source_index, create_target_index
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

        units = self.get_units(*args, **options)

        update_index(units)
