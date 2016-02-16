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

from optparse import make_option

from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.http.request import HttpRequest

from weblate.accounts.models import get_author_name
from weblate.trans.management.commands import WeblateTranslationCommand


class Command(WeblateTranslationCommand):
    """WeblateTranslationCommand
    Command for mass importing suggestions.
    """
    help = 'imports suggestions'
    args = '<project> <component> <language> <file>'
    option_list = WeblateTranslationCommand.option_list + (
        make_option(
            '--author',
            default='noreply@weblate.org',
            help=(
                'Email address of author (has to be registered in Weblate)'
            )
        ),
    )

    def handle(self, *args, **options):
        # Check params
        if len(args) != 4:
            raise CommandError('Invalid number of parameters!')

        # Get translation object
        translation = self.get_translation(args)

        # Get user
        try:
            user = User.objects.get(email=options['author'])
        except User.DoesNotExist:
            raise CommandError('Import user does not exist!')

        # Create fake request object
        request = HttpRequest()
        request.user = user

        # Process import
        try:
            with open(args[3], 'rb') as handle:
                translation.merge_upload(
                    request, handle, False, method='suggest',
                    author=get_author_name(user),
                )
        except IOError:
            raise CommandError('Failed to import translation file!')
