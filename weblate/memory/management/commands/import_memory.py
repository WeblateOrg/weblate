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

from __future__ import unicode_literals

import argparse
import json

from django.core.management.base import BaseCommand, CommandError

from weblate.memory.storage import TranslationMemory, MemoryImportError


class Command(BaseCommand):
    """
    Command for importing translation memory.
    """
    help = 'imports translation memory'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--language-map',
            help='Map language codes in the TMX to Weblate, eg. en_US:en'
        )
        parser.add_argument(
            'file',
            type=argparse.FileType('r'),
            help='File to import (TMX or JSON)',
        )

    def handle(self, *args, **options):
        """Translation memory import."""
        langmap = None
        if options['language_map']:
            langmap = {
                x: y for (x, y) in (
                    z.split(':', 1) for z in options['language_map'].split(',')
                )
            }

        try:
            TranslationMemory.import_file(options['file'], langmap)
        except MemoryImportError as error:
            raise CommandError('Import failed: {}'.format(error))
