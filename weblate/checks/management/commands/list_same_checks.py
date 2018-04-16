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
from django.core.management.base import BaseCommand
from django.db.models import Count
from weblate.checks.models import Check


class Command(BaseCommand):
    help = 'lists top not translated failing checks'

    def handle(self, *args, **options):
        results = Check.objects.filter(
            check='same'
        ).values(
            'content_hash'
        ).annotate(
            Count('content_hash')
        ).filter(
            content_hash__count__gt=1
        ).order_by(
            '-content_hash__count'
        )

        for item in results:
            check = Check.objects.filter(
                check='same',
                content_hash=item['content_hash']
            )[0]

            units = check.related_units
            if not units.exists():
                continue

            self.stdout.write(
                '{0:5d} {1}'.format(
                    item['content_hash__count'],
                    units[0].source,
                )
            )
