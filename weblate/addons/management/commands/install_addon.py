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

import json

from django.core.management.base import CommandError

from weblate.addons.models import ADDONS, Addon
from weblate.auth.models import User, get_anonymous
from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = 'installs addon to all listed components'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--addon',
            required=True,
            help='Addon name'
        )
        parser.add_argument(
            '--configuration',
            default='{}',
            help='Addon configuration in JSON'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing addons configuration'
        )

    def handle(self, *args, **options):
        try:
            addon = ADDONS[options['addon']]()
        except KeyError:
            raise CommandError('Addon not found: {}'.format(options['addon']))
        try:
            configuration = json.loads(options['configuration'])
        except ValueError as error:
            raise CommandError('Invalid addon configuration: {}'.format(error))
        if addon.has_settings:
            form = addon.get_add_form(None, data=configuration)
            if not form.is_valid():
                for error in form.non_field_errors():
                    self.stderr.write(error)
                for field in form:
                    for error in field.errors:
                        self.stderr.write(
                            'Error in {}: {}'.format(field.name, error)
                        )
                raise CommandError(
                    'Invalid addon configuration!'
                )
        try:
            user = User.objects.filter(is_superuser=True)[0]
        except IndexError:
            user = get_anonymous()
        for component in self.get_components(*args, **options):
            addons = Addon.objects.filter_component(component).filter(
                name=addon.name
            )
            if addons.exists():
                if options['update']:
                    addons.update(configuration=configuration)
                    self.stdout.write(
                        'Successfully updated on {}'.format(component)
                    )
                else:
                    self.stderr.write(
                        'Already installed on {}'.format(component)
                    )
                continue

            if not addon.can_install(component, user):
                self.stderr.write('Can not install on {}'.format(component))
                continue

            addon.create(component, configuration=configuration)
            self.stdout.write(
                'Successfully installed on {}'.format(component)
            )
