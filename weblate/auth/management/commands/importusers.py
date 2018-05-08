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

from django.core.management.base import BaseCommand
from weblate.auth.models import User


class Command(BaseCommand):
    help = 'imports users from JSON dump of database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Only check import, do not actually create users'
        )
        parser.add_argument(
            'json-file',
            type=argparse.FileType('r'),
            help='JSON file containing user dump to import',
        )

    def handle(self, *args, **options):
        """Create default set of groups and optionally updates them and moves
        users around to default group.
        """

        data = json.load(options['json-file'])
        options['json-file'].close()

        for line in data:
            if 'fields' in line:
                line = line['fields']

            if 'is_active' in line and not line['is_active']:
                continue

            if not line['email'] or not line['username']:
                self.stderr.write(
                    'Skipping {0}, has blank username or email'.format(line)
                )
                continue

            if User.objects.filter(username=line['username']).exists():
                self.stderr.write(
                    'Skipping {0}, username exists'.format(line['username'])
                )
                continue

            if User.objects.filter(email=line['email']).exists():
                self.stderr.write(
                    'Skipping {0}, email exists'.format(line['email'])
                )
                continue

            if line['last_name'] not in line['first_name']:
                full_name = '{0} {1}'.format(
                    line['first_name'],
                    line['last_name']
                )
            else:
                full_name = line['first_name']

            if not options['check']:
                User.objects.create(
                    username=line['username'],
                    full_name=full_name,
                    password=line['password'],
                    email=line['email']
                )
