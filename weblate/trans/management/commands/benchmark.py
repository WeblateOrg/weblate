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

from weblate.trans.models import SubProject, Project
from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
import cProfile
import pstats


class Command(BaseCommand):
    '''
    Runs simple project import to perform benchmarks.
    '''
    help = 'performs import benchmark'
    args = '<project> <repo> <mask>'
    option_list = BaseCommand.option_list + (
        make_option(
            '--profile-sort',
            type='str',
            dest='profile_sort',
            default='cumulative',
            help='sort order for profile stats',
        ),
        make_option(
            '--profile-count',
            type='int',
            dest='profile_count',
            default=20,
            help='number of profile stats to show',
        ),
    )

    def handle(self, *args, **options):
        if len(args) < 3:
            raise CommandError('Missing arguments!')
        project = Project.objects.get(slug=args[0])
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
            repo=args[1],
            filemask=args[2],
            project=project
        )
        stats = pstats.Stats(profiler)
        stats.sort_stats(options['profile_sort'])
        stats.print_stats(options['profile_count'])
        # Delete after testing
        subproject.delete()
