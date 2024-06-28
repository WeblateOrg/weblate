# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json

from django.core.serializers.json import DjangoJSONEncoder

from weblate.accounts.models import Profile
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "dumps user data to JSON file"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "json-file", type=argparse.FileType("w"), help="File where to export"
        )

    def handle(self, *args, **options) -> None:
        data = []

        profiles = Profile.objects.select_related("user").prefetch_related(
            "watched", "languages", "secondary_languages"
        )

        for profile in profiles:
            if not profile.user.is_active or profile.user.is_bot:
                continue
            data.append(profile.dump_data())

        json.dump(data, options["json-file"], indent=2, cls=DjangoJSONEncoder)
        options["json-file"].close()
