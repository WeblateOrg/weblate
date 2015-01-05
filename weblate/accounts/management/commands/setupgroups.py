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
from weblate.accounts.models import create_groups, move_users


class Command(BaseCommand):
    help = 'setups default user groups'
    option_list = BaseCommand.option_list + (
        make_option(
            '--move',
            action='store_true',
            dest='move',
            default=False,
            help='Move all users to Users group'
        ),
        make_option(
            '--no-privs-update',
            action='store_false',
            dest='update',
            default=True,
            help='Prevents updates of privileges of existing groups'
        ),
    )

    def handle(self, *args, **options):
        '''
        Creates default set of groups and optionally updates them and moves
        users around to default group.
        '''
        create_groups(options['update'])
        if options['move']:
            move_users()
