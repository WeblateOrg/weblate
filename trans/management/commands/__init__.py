# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
'''
Helper classes for management commands.
'''

from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
from trans.models import Unit, SubProject


class WeblateCommand(BaseCommand):
    '''
    Command which accepts project/subproject/--all params to process.
    '''
    args = '<project/subproject>'
    option_list = BaseCommand.option_list + (
        make_option(
            '--all',
            action='store_true',
            dest='all',
            default=False,
            help='process all subprojects'
        ),
    )

    def get_units(self, *args, **options):
        '''
        Returns list of units matching parameters.
        '''
        translations = self.get_translations(*args, **options)
        return Unit.objects.filter(translation__in=translations)

    def get_translations(self, *args, **options):
        '''
        Returns list of translations matching parameters.
        '''
        return self.get_subprojects.translation_set.all()

    def get_subprojects(self, *args, **options):
        '''
        Returns list of subprojects matching parameters.
        '''
        if options['all']:
            # all subprojects
            result = SubProject.objects.all()
        elif len(args) == 0:
            # no argumets to filter projects
            print 'Please specify either --all or <project/subproject>'
            raise CommandError('Nothing to process!')
        else:
            # start with none and add found
            result = SubProject.objects.none()

            # process arguments
            for arg in args:
                # do we have also subproject?
                parts = arg.split('/')

                # filter by project
                found = SubProject.objects.filter(project__slug=parts[0])

                # filter by subproject if available
                if len(parts) == 2:
                    found = found.filter(slug=parts[1])

                # warn on no match
                if found.count() == 0:
                    print '"%s" did not match any subproject' % arg
                    raise CommandError('Nothing to process!')

                # merge results
                result |= found

        return result

    def handle(self, *args, **options):
        """
        The actual logic of the command. Subclasses must implement
        this method.

        """
        raise NotImplementedError()


class WeblateLangCommand(WeblateCommand):
    '''
    Command accepting additional language parameter to filter
    list of languages to process.
    '''
    option_list = WeblateCommand.option_list + (
        make_option(
            '--lang',
            action='store',
            type='string',
            dest='lang',
            default=None,
            help='Limit only to given languages (comma separated list)'
        ),
    )

    def get_translations(self, *args, **options):
        '''
        Returns list of translations matching parameters.
        '''
        result = super(WeblateLangCommand, self).get_translations(
            *args, **options
        )

        if options['lang'] is not None:
            langs = options['lang'].split(',')
            result = result.filter(language_code__in=langs)

        return result

    def handle(self, *args, **options):
        """
        The actual logic of the command. Subclasses must implement
        this method.

        """
        raise NotImplementedError()
