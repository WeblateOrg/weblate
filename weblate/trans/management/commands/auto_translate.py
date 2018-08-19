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

from django.core.management.base import CommandError
from django.http.request import HttpRequest

from weblate.auth.models import User
from weblate.accounts.models import Profile
from weblate.trans.models import Component
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.management.commands import WeblateTranslationCommand


class Command(WeblateTranslationCommand):
    """
    Command for mass automatic translation.
    """
    help = 'performs automatic translation based on other components'

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            '--user',
            default='anonymous',
            help=(
                'User performing the change'
            )
        )
        parser.add_argument(
            '--source',
            default='',
            help=(
                'Source component <project/component>'
            )
        )
        parser.add_argument(
            '--add',
            default=False,
            action='store_true',
            help=(
                'Add translations if they do not exist'
            )
        )
        parser.add_argument(
            '--overwrite',
            default=False,
            action='store_true',
            help=(
                'Overwrite existing translations in target component'
            )
        )
        parser.add_argument(
            '--inconsistent',
            default=False,
            action='store_true',
            help=(
                'Process only inconsistent translations'
            )
        )

    def handle(self, *args, **options):
        # Get translation object
        translation = self.get_translation(**options)

        # Get user
        try:
            user = User.objects.get(username=options['user'])
            Profile.objects.get_or_create(user=user)
        except User.DoesNotExist:
            raise CommandError('User does not exist!')

        if options['source']:
            parts = options['source'].split('/')
            if len(parts) != 2:
                raise CommandError('Invalid source component specified!')
            try:
                component = Component.objects.get(
                    project__slug=parts[0],
                    slug=parts[1],
                )
            except Component.DoesNotExist:
                raise CommandError('No matching source component found!')
            source = component.id
        else:
            source = ''

        if options['inconsistent']:
            filter_type = 'check:inconsistent'
        elif options['overwrite']:
            filter_type = 'all'
        else:
            filter_type = 'todo'
        # Create fake request object
        request = HttpRequest()
        request.user = user
        auto = AutoTranslate(user, translation, filter_type, request)
        auto.process_others(source, check_acl=False)
        self.stdout.write('Updated {0} units'.format(auto.updated))
