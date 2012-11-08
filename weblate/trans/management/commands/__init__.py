# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from optparse import make_option
from weblate.trans.models import Unit

class UnitCommand(BaseCommand):
    '''
    Command which accepts project/subproject/--all params to process units.
    '''
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option('--all',
            action='store_true',
            dest='all',
            default=False,
            help='work on all projects'),
        )

    def get_units(self, *args, **options):
        '''
        Returns list of units matching parameters.
        '''
        if options['all']:
            base = Unit.objects.all()
        else:
            base = Unit.objects.none()
            for arg in args:
                parts = arg.split('/')
                if len(parts) == 2:
                    prj, subprj = parts
                    base |= Unit.objects.filter(
                        translation__subproject__slug = subprj,
                        translation__subproject__project__slug = prj
                    )
                else:
                    prj = parts[0]
                    base |= Unit.objects.filter(translation__subproject__project__slug = prj)
            else:
                print 'Nothing to process, please use either --all or <project/subproject>'
        return base

