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

import cProfile
import pstats

from django.core.management.base import BaseCommand

from weblate.trans.models import SubProject, Project


class Command(BaseCommand):
    '''
    Runs simple project import to perform benchmarks.
    '''
    help = 'performs import benchmark'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--profile-sort',
            dest='profile_sort',
            default='cumulative',
            help='sort order for profile stats',
        )
        parser.add_argument(
            '--profile-count',
            type=int,
            dest='profile_count',
            default=20,
            help='number of profile stats to show',
        )
        parser.add_argument(
            'project',
            help='Existing project slug for tests',
        )
        parser.add_argument(
            'repo',
            help='Test VCS repository URL',
        )
        parser.add_argument(
            'mask',
            help='File mask',
        )

    def handle(self, *args, **options):
        project = Project.objects.get(slug=options['project'])
        # Delete any possible previous tests
        SubProject.objects.filter(
            project=project,
            slug='benchmark'
        ).delete()
        profiler = cProfile.Profile()
        subproject = profiler.runcall(
            SubProject.objects.create,
            name='Benchmark',
            slug='benchmark',
            repo=options['repo'],
            filemask=options['mask'],
            project=project
        )
        stats = pstats.Stats(profiler)
        stats.sort_stats(options['profile_sort'])
        stats.print_stats(options['profile_count'])
        # Delete after testing
        subproject.delete()
