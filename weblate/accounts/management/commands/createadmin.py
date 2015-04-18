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
from django.contrib.auth.models import User
import string
import os
import random


class Command(BaseCommand):
    help = 'setups admin user with admin password (INSECURE!)'

    @staticmethod
    def make_password(length):
        chars = string.ascii_letters + string.digits + '!@#$%^&*()'
        random.seed = (os.urandom(1024))
        return ''.join(random.choice(chars) for i in range(length))

    def handle(self, *args, **options):
        '''
        Create admin account with admin password.

        This is useful mostly for setup inside appliances, when user wants
        to be able to login remotely and change password then.
        '''

        password = self.make_password(13)
        self.stdout.write('Creating user admin with password ' + password)
        user = User.objects.create_user('admin', 'admin@example.com', password)
        user.first_name = 'Weblate Admin'
        user.last_name = ''
        user.is_superuser = True
        user.is_staff = True
        user.is_active = True
        user.save()
