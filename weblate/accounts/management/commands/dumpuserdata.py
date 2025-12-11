# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from django.core.management.base import CommandError
from django.core.serializers.json import DjangoJSONEncoder

from weblate.accounts.models import Profile
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "dumps user data to JSON file"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("json-file", type=Path, help="File where to export")

    def handle(self, *args, **options) -> None:
        data = []

        profiles = Profile.objects.select_related("user").prefetch_related(
            "watched", "languages", "secondary_languages"
        )

        for profile in profiles:
            if not profile.user.is_active or profile.user.is_bot:
                continue
            data.append(profile.dump_data())

        try:
            with options["json-file"].open("w") as handle:
                json.dump(data, handle, indent=2, cls=DjangoJSONEncoder)
        except OSError as error:
            msg = f"Could not open file: {error}"
            raise CommandError(msg) from error
