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

from django.core.management.base import BaseCommand

from weblate.memory.storage import TranslationMemory


class Command(BaseCommand):
    """
    Command for importing translation memory from TMX.
    """
    help = 'imports translation memory for TMX'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--language-map',
            help='Map language codes in the TMX to Weblate, eg. en_US:en'
        )
        parser.add_argument(
            'tmx-file',
            type=argparse.FileType('r'),
            help='TMX file to import',
        )

    def handle(self, *args, **options):
        """TMX memory import."""
        langmap = None
        if options['language_map']:
            langmap = {
                x: y for (x, y) in (
                    z.split(':', 1) for z in options['language_map'].split(',')
                )
            }
        TranslationMemory().import_tmx(options['tmx-file'], langmap)
