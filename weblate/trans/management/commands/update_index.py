# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.management.base import BaseCommand
from django.db import transaction

from weblate.trans.models import IndexUpdate, Unit
from weblate.trans.search import update_index, delete_search_unit


class Command(BaseCommand):
    help = 'updates index for fulltext search'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--limit',
            action='store',
            type=int,
            dest='limit',
            default=1000,
            help='number of updates to process in one run'
        )

    def handle(self, *args, **options):
        self.do_update(options['limit'])
        self.do_delete(options['limit'])

    def do_delete(self, limit):
        indexupdates = set()

        # Grab all updates from the database
        with transaction.atomic():
            updates = IndexUpdate.objects.filter(to_delete=True)
            for update in updates[:limit].iterator():
                indexupdates.add(update.pk)
                delete_search_unit(
                    update.unitid,
                    update.language_code
                )

        # Delete processed updates
        with transaction.atomic():
            IndexUpdate.objects.filter(id__in=indexupdates).delete()

    def do_update(self, limit):
        indexupdates = set()
        unit_ids = set()
        source_unit_ids = set()

        # Grab all updates from the database
        with transaction.atomic():
            updates = IndexUpdate.objects.filter(to_delete=False)
            for update in updates[:limit].iterator():
                indexupdates.add(update.pk)
                unit_ids.add(update.unitid)

                if update.source:
                    source_unit_ids.add(update.unitid)

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
        with transaction.atomic():
            IndexUpdate.objects.filter(id__in=indexupdates).delete()
