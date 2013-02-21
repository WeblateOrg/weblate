# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from trans.models import IndexUpdate, Unit
from trans.search import update_index


class Command(BaseCommand):
    help = 'updates index for fulltext search'

    def handle(self, *args, **options):
        # Grab all updates from the database
        updates = list(IndexUpdate.objects.all())

        # Grab just IDs
        update_ids = [update.id for update in updates]
        source_update_ids = [update.id for update in updates if update.source]

        # Filter matching units
        units = Unit.objects.filter(
            indexupdate__id__in=update_ids
        )
        source_units = Unit.objects.filter(
            indexupdate__id__in=source_update_ids
        )

        # Udate index
        update_index(units, source_units)

        # Delete processed updates
        IndexUpdate.objects.filter(id__in=update_ids).delete()
