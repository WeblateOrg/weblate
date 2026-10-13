# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from django.core.management.base import CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch

from weblate.accounts.models import Profile, Subscription, load_subscription_categories
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "dumps user data to JSON file"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("json-file", type=Path, help="File where to export")

    def handle(self, *args, **options) -> None:
        profiles = list(
            Profile.objects.filter(user__is_active=True, user__is_bot=False)
            .select_related("user")
            .prefetch_related(
                "watched",
                "languages",
                "secondary_languages",
                Prefetch(
                    "user__subscription_set",
                    queryset=Subscription.objects.select_related(
                        "project", "component", "component__project"
                    ),
                ),
            )
        )
        categories = load_subscription_categories(
            subscription
            for profile in profiles
            for subscription in profile.user.subscription_set.all()
        )

        data = [
            profile.dump_data(
                subscriptions=profile.user.subscription_set.all(),
                categories=categories,
            )
            for profile in profiles
        ]

        try:
            with options["json-file"].open("w") as handle:
                json.dump(data, handle, indent=2, cls=DjangoJSONEncoder)
        except OSError as error:
            msg = f"Could not open file: {error}"
            raise CommandError(msg) from error
