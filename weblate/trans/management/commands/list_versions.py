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

import platform

from django.conf import settings
from django.core.management.base import BaseCommand
from django import db

from weblate.utils.requirements import get_versions_string


class Command(BaseCommand):
    help = 'lists versions of required software components'

    def handle(self, *args, **options):
        """Print versions of dependencies."""
        self.stdout.write(get_versions_string())
        self.stdout.write(
            ' * Database backends: ' +
            ', '.join(
                [conn['ENGINE'] for conn in db.connections.databases.values()]
            )
        )
        self.stdout.write(
            ' * Cache backends: ' +
            ', '.join(
                '{}:{}'.format(key, value['BACKEND'].split('.')[-1])
                for key, value in settings.CACHES.items()
            )
        )
        self.stdout.write(
            ' * Platform: {} {} ({})'.format(
                platform.system(),
                platform.release(),
                platform.machine(),
            )
        )
