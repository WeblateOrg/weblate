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

from django.core.management.base import BaseCommand

from weblate.memory.storage import TranslationMemory


class Command(BaseCommand):
    help = 'list translation memory origins'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--type',
            choices=['origin', 'category'],
            default='origin',
            required=False,
            help='Type of objects to list',
        )

    def handle(self, *args, **options):
        """Translation memory cleanup."""
        memory = TranslationMemory()
        for item in memory.get_values(options['type']):
            self.stdout.write(item)
