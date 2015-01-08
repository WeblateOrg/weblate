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

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
import json


class Command(BaseCommand):
    help = 'imports users from JSON dump of database'
    args = '<json-file>'

    def handle(self, *args, **options):
        '''
        Creates default set of groups and optionally updates them and moves
        users around to default group.
        '''
        if len(args) != 1:
            raise CommandError('Please specify JSON file to import!')

        data = json.load(open(args[0]))

        for line in data:
            if 'fields' in line:
                line = line['fields']

            if User.objects.filter(username=line['username']).exists():
                self.stdout.write(
                    'Skipping {}, username exists'.format(line['username'])
                )
                continue

            if User.objects.filter(email=line['email']).exists():
                self.stdout.write(
                    'Skipping {}, email exists'.format(line['email'])
                )
                continue

            if not line['last_name'] in line['first_name']:
                full_name = u'{0} {1}'.format(
                    line['first_name'],
                    line['last_name']
                )
            else:
                full_name = line['first_name']

            User.objects.create(
                username=line['username'],
                first_name=full_name,
                last_name='',
                password=line['password'],
                email=line['email']
            )
