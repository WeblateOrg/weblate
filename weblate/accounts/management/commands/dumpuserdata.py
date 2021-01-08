#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.core.serializers.json import DjangoJSONEncoder

from weblate.accounts.models import Profile
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "dumps user data to JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "json-file", type=argparse.FileType("w"), help="File where to export"
        )

    def handle(self, *args, **options):
        data = []

        profiles = Profile.objects.select_related("user").prefetch_related(
            "watched", "languages", "secondary_languages"
        )

        for profile in profiles:
            if not profile.user.is_active:
                continue
            data.append(profile.dump_data())

        json.dump(data, options["json-file"], indent=2, cls=DjangoJSONEncoder)
        options["json-file"].close()
