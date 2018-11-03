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
from django.contrib.sites.models import Site

from weblate.utils.site import check_domain


class Command(BaseCommand):
    help = 'changes default site name'

    def add_arguments(self, parser):
        parser.add_argument(
            '--set-name',
            dest='set_name',
            default=None,
            help='site name to set'
        )
        parser.add_argument(
            '--site-id',
            type=int,
            dest='site_id',
            default=1,
            help='site ID to manipulate (1 by default)'
        )
        parser.add_argument(
            '--get-name',
            action='store_true',
            dest='get_name',
            default=False,
            help='just display the site name'
        )

    def handle(self, *args, **options):
        if options['set_name']:
            if not check_domain(options['set_name']):
                raise CommandError('Please provide valid domain name!')
            site, created = Site.objects.get_or_create(
                pk=options['site_id'],
                defaults={
                    'domain': options['set_name'],
                    'name': options['set_name']
                }
            )
            if not created:
                site.domain = options['set_name']
                site.name = options['set_name']
                site.save()
        elif options['get_name']:
            try:
                site = Site.objects.get(pk=options['site_id'])
                self.stdout.write(site.domain)
            except Site.DoesNotExist:
                raise CommandError('Site does not exist!')
        else:
            raise CommandError('Please specify desired action!')
