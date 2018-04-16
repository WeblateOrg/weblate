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

from django.core.management.base import BaseCommand

from weblate.checks.models import Check


class Command(BaseCommand):
    help = 'lists top ignored checks'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--count',
            type=int,
            dest='count',
            default=100,
            help='Number of top checks to list',
        )
        parser.add_argument(
            '--list-all',
            action='store_true',
            dest='list_all',
            default=False,
            help='List all checks (not only ignored)',
        )

    def handle(self, *args, **options):
        results = {}
        if options['list_all']:
            checks = Check.objects.all()
        else:
            checks = Check.objects.filter(ignore=True)
        for check in checks:
            name = '{0}-{1}'.format(check.check, check.content_hash)
            units = check.related_units
            if not units.exists():
                continue
            if name in results:
                results[name]['count'] += 1
            else:
                results[name] = {
                    'count': 1,
                    'check': check.check,
                    'source': units[0].source,
                }
        results = sorted(results.values(), key=lambda x: -x['count'])
        for result in results[:options['count']]:
            self.stdout.write(
                '{count:5d} {check:20} {source}'.format(**result)
            )
