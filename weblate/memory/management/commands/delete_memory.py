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

from django.core.management.base import BaseCommand, CommandError

from weblate.memory.storage import TranslationMemory


class Command(BaseCommand):
    """
    Command for deleting translation memory content.
    """
    help = 'deletes translation memory content'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--origin',
            help='Origin to remove',
        )
        parser.add_argument(
            '--category',
            help='Category to remove',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Remove all entries',
            default=False
        )

    def handle(self, *args, **options):
        """Translation memory cleanup."""
        memory = TranslationMemory()
        if options['all']:
            memory.empty()
        elif options['origin'] or options['category']:
            memory.delete(options['origin'], options['category'])
        else:
            raise CommandError('Please specify what you want to delete')
