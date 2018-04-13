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

from textwrap import wrap

from django.core.management.base import BaseCommand

from weblate.addons.models import ADDONS


class Command(BaseCommand):
    help = 'List installed addons'

    def handle(self, *args, **options):
        """Create default set of languages, optionally updating them
        to match current shipped definitions.
        """
        for dummy, obj in sorted(ADDONS.items()):
            self.stdout.write('.. _addon-{}:'.format(obj.name))
            self.stdout.write('\n')
            self.stdout.write(obj.verbose)
            self.stdout.write('-' * len(obj.verbose))
            self.stdout.write('\n')
            self.stdout.write('\n'.join(wrap(obj.description, 79)))
            self.stdout.write('\n')
