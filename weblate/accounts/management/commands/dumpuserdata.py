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

from django.core.management.base import BaseCommand, CommandError
from weblate.accounts.models import Profile
import json


class Command(BaseCommand):
    help = 'dumps user data to JSON file'
    args = '<json-file>'

    def handle(self, *args, **options):
        '''
        Creates default set of groups and optionally updates them and moves
        users around to default group.
        '''
        if len(args) != 1:
            raise CommandError('Please specify JSON file to create!')

        data = []
        fields = (
            'language',
            'translated',
            'suggested',
        ) + Profile.SUBSCRIPTION_FIELDS

        profiles = Profile.objects.select_related(
            'user'
        ).prefetch_related(
            'subscriptions', 'languages', 'secondary_languages'
        )

        for profile in profiles.iterator():
            if not profile.user.is_active:
                continue

            item = {
                'username': profile.user.username,
                'subscriptions': [
                    p.slug for p in profile.subscriptions.all()
                ],
                'languages': [
                    l.code for l in profile.languages.all()
                ],
                'secondary_languages': [
                    l.code for l in profile.secondary_languages.all()
                ],
            }

            for field in fields:
                item[field] = getattr(profile, field)

            data.append(item)

        json.dump(data, open(args[0], 'w'), indent=2)
