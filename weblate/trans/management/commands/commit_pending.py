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

from weblate.trans.management.commands import WeblateLangCommand
from django.utils import timezone
from datetime import timedelta
from optparse import make_option


class Command(WeblateLangCommand):
    help = 'commits pending changes older than given age'
    option_list = WeblateLangCommand.option_list + (
        make_option(
            '--age',
            action='store',
            type='int',
            dest='age',
            default=24,
            help='Age of changes to commit in hours (default is 24 hours)'
        ),
    )

    def handle(self, *args, **options):

        age = timezone.now() - timedelta(hours=options['age'])

        for translation in self.get_translations(*args, **options):
            if not translation.git_needs_commit():
                continue

            last_change = translation.last_change
            if last_change is None:
                continue
            if last_change > age:
                continue

            if int(options['verbosity']) >= 1:
                self.stdout.write('Committing %s' % translation)
            translation.commit_pending(None)
