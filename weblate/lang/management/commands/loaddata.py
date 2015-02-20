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

from django.core.management.commands.loaddata import Command as DjangoCommand
from django.db import transaction

from weblate.lang.models import Language
from weblate.accounts.models import create_groups


class Command(DjangoCommand):
    def loaddata(self, fixture_labels):
        '''
        Hook for creating basic set of languages on database migration.
        '''
        if self.app_label == 'weblate' and fixture_labels == ('initial_data',):
            with transaction.atomic():
                Language.objects.setup(False)
                create_groups(False)
        super(Command, self).loaddata(fixture_labels)
