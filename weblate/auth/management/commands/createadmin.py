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

from random import SystemRandom
import string

from django.core.management.base import BaseCommand, CommandError
from weblate.auth.models import User


class Command(BaseCommand):
    help = 'setups admin user with random password'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=None,
            help='Password to set, random is generated if not specified'
        )
        parser.add_argument(
            '--no-password',
            action='store_true',
            default=False,
            help='Do not set password at all (useful with --update)'
        )
        parser.add_argument(
            '--username',
            default='admin',
            help='Admin username, defaults to "admin"'
        )
        parser.add_argument(
            '--email',
            default='admin@example.com',
            help='Admin email, defaults to "admin@example.com"'
        )
        parser.add_argument(
            '--name',
            default='Weblate Admin',
            help='Admin name, defaults to "Weblate Admin"'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            default=False,
            help='Change password for this account if exists'
        )

    @staticmethod
    def make_password(length):
        generator = SystemRandom()
        chars = string.ascii_letters + string.digits + '!@#$%^&*()'
        return ''.join(generator.choice(chars) for i in range(length))

    def handle(self, *args, **options):
        """Create admin account with admin password.

        This is useful mostly for setup inside appliances, when user wants
        to be able to login remotely and change password then.
        """
        exists = User.objects.filter(username=options['username']).exists()
        if exists and not options['update']:
            raise CommandError(
                'User exists, specify --update to update existing'
            )

        if options['no_password']:
            password = None
        elif options['password']:
            password = options['password']
            self.stdout.write('Creating user admin')
        else:
            password = self.make_password(13)
            self.stdout.write('Creating user admin with password ' + password)

        if exists and options['update']:
            user = User.objects.get(username=options['username'])
            user.email = options['email']
            if password is not None:
                user.set_password(password)
        else:
            user = User.objects.create_user(
                options['username'],
                options['email'],
                password
            )
        user.full_name = options['name']
        user.is_superuser = True
        user.is_active = True
        user.save()
