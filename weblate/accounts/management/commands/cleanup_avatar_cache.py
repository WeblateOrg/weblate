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

from glob import glob
import pickle
import os
import zlib

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'removes incompatible files from avatar cache'

    def handle(self, *args, **options):
        backends = (
            'django.core.cache.backends.filebased.FileBasedCache',
        )
        if 'avatar' not in settings.CACHES:
            return
        if settings.CACHES['avatar']['BACKEND'] not in backends:
            return
        mask = os.path.join(
            settings.CACHES['avatar']['LOCATION'],
            '*.djcache'
        )
        for name in glob(mask):
            with open(name, 'rb') as handle:
                try:
                    # Load expiry
                    pickle.load(handle)
                    # Load payload
                    pickle.loads(zlib.decompress(handle.read()))
                except Exception as error:
                    self.stdout.write('Removing {}: {}'.format(name, error))
                    os.remove(name)
