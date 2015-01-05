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
from weblate.trans.models import IndexUpdate, Unit
from weblate.trans.search import update_index


class Command(BaseCommand):
    help = 'updates index for fulltext search'

    def handle(self, *args, **options):
        indexupdates = set()
        unit_ids = set()
        source_unit_ids = set()

        # Grab all updates from the database
        for update in IndexUpdate.objects.iterator():
            indexupdates.add(update.pk)
            unit_ids.add(update.unit_id)

            if update.source:
                source_unit_ids.add(update.unit_id)

        # Filter matching units
        units = Unit.objects.filter(
            id__in=unit_ids
        )
        source_units = Unit.objects.filter(
            id__in=source_unit_ids
        )

        # Udate index
        update_index(units, source_units)

        # Delete processed updates
        IndexUpdate.objects.filter(id__in=indexupdates).delete()
