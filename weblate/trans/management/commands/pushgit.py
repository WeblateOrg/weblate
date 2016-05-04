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

from weblate.trans.management.commands import WeblateCommand


class Command(WeblateCommand):
    help = 'pushes all changes to upstream respository'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--force-commit',
            action='store_true',
            dest='force_commit',
            default=False,
            help='Forces commiting pending changes'
        )

    def handle(self, *args, **options):
        for subproject in self.get_subprojects(**options):
            subproject.do_push(None, force_commit=options['force_commit'])
