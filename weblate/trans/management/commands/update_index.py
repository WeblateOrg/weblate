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

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from whoosh.index import LockError

from weblate.trans.models import IndexUpdate, Unit
from weblate.trans.search import Fulltext


class Command(BaseCommand):
    help = 'updates index for fulltext search'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--limit',
            action='store',
            type=int,
            dest='limit',
            default=10000,
            help='number of updates to process in one run'
        )

    def handle(self, *args, **options):
        try:
            fulltext = Fulltext()
            self.do_update(fulltext, options['limit'])
            self.do_delete(fulltext, options['limit'])
        except LockError:
            raise CommandError(
                'Failed to acquire lock on the fulltext index, '
                'probably some other update is already running.'
            )

    def do_delete(self, fulltext, limit):
        indexupdates = set()

        langupdates = {}

        # Grab all updates from the database
        with transaction.atomic():
            updates = IndexUpdate.objects.filter(to_delete=True)
            for update in updates[:limit].iterator():
                indexupdates.add(update.pk)
                if update.language_code not in langupdates:
                    langupdates[update.language_code] = set()
                langupdates[update.language_code].add(update.pk)

        fulltext.delete_search_units(
            indexupdates,
            langupdates,
        )

        # Delete processed updates
        with transaction.atomic():
            IndexUpdate.objects.filter(id__in=indexupdates).delete()

    def do_update(self, fulltext, limit):
        indexupdates = set()
        unit_ids = set()

        # Grab all updates from the database
        with transaction.atomic():
            updates = IndexUpdate.objects.filter(to_delete=False)
            for update in updates[:limit].iterator():
                indexupdates.add(update.pk)
                unit_ids.add(update.unitid)

        # Filter matching units
        units = Unit.objects.filter(
            id__in=unit_ids
        )

        # Udate index
        fulltext.update_index(units)

        # Delete processed updates
        with transaction.atomic():
            IndexUpdate.objects.filter(id__in=indexupdates).delete()
