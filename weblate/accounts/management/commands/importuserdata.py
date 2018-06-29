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

import argparse
import json

from django.core.management.base import BaseCommand
from weblate.auth.models import User

from weblate.accounts.models import Profile
from weblate.lang.models import Language
from weblate.trans.models import Project


class Command(BaseCommand):
    help = 'imports userdata from JSON dump of database'

    def add_arguments(self, parser):
        parser.add_argument(
            'json-file',
            type=argparse.FileType('r'),
            help='JSON file containing user data to import',
        )

    @staticmethod
    def import_subscriptions(profile, userprofile):
        """Import user subscriptions."""
        # Add subscriptions
        for subscription in userprofile['subscriptions']:
            try:
                profile.subscriptions.add(
                    Project.objects.get(slug=subscription)
                )
            except Project.DoesNotExist:
                continue

        # Subscription settings
        for field in Profile.SUBSCRIPTION_FIELDS:
            setattr(profile, field, userprofile[field])

    @staticmethod
    def update_languages(profile, userprofile):
        """Update user language preferences."""
        profile.language = userprofile['language']
        for lang in userprofile['secondary_languages']:
            profile.secondary_languages.add(
                Language.objects.auto_get_or_create(lang)
            )
        for lang in userprofile['languages']:
            profile.languages.add(
                Language.objects.auto_get_or_create(lang)
            )

    def handle(self, **options):
        """Create default set of groups.

        Also ptionally updates them and moves users around to default group.
        """
        userdata = json.load(options['json-file'])
        options['json-file'].close()

        for userprofile in userdata:
            try:
                user = User.objects.get(username=userprofile['username'])
                update = False
                try:
                    profile = Profile.objects.get(user=user)
                    if not profile.language:
                        update = True
                except Profile.DoesNotExist:
                    update = True
                    profile = Profile.objects.create(user=user)
                    self.stdout.write(
                        'Creating profile for {0}'.format(
                            userprofile['username']
                        )
                    )

                # Merge stats
                profile.translated += userprofile['translated']
                profile.suggested += userprofile['suggested']

                # Update fields if we should
                if update:
                    self.update_languages(profile, userprofile)

                # Add subscriptions
                self.import_subscriptions(profile, userprofile)

                profile.save()
            except User.DoesNotExist:
                self.stderr.write(
                    'User not found: {0}\n'.format(userprofile['username'])
                )
