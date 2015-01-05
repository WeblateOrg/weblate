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

from django.core.management.base import BaseCommand
from optparse import make_option
from weblate.lang.models import Language


class Command(BaseCommand):
    help = 'Populates language definitions'

    option_list = BaseCommand.option_list + (
        make_option(
            '--no-update',
            action='store_false',
            dest='update',
            default=True,
            help='Prevents updates to existing language definitions'
        ),
    )

    def handle(self, *args, **options):
        '''
        Creates default set of languages, optionally updating them
        to match current shipped definitions.
        '''
        Language.objects.setup(options['update'])
