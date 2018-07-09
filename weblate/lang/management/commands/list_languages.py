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
from django.utils.translation import activate, ugettext

from weblate.lang.models import Language


class Command(BaseCommand):
    help = 'List language definitions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--lower',
            action='store_true',
            help='Lowercase translated name',
        )
        parser.add_argument(
            'locale',
            help='Locale for printing',
        )

    def handle(self, *args, **options):
        """Create default set of languages, optionally updating them
        to match current shipped definitions.
        """
        activate(options['locale'])
        for language in Language.objects.order_by('name'):
            name = ugettext(language.name)
            if options['lower']:
                name = name[0].lower() + name[1:]
            self.stdout.write(
                '| {0} || {1} || {2}'.format(
                    language.code,
                    language.name,
                    name,
                )
            )
            self.stdout.write('|-')
