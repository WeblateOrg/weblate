# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "imports userdata from JSON dump of database"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "json-file",
            type=argparse.FileType("r"),
            help="JSON file containing user data to import",
        )

    @staticmethod
    def import_watched(profile, userprofile) -> None:
        """Import user subscriptions."""
        # Add subscriptions
        for subscription in userprofile["watched"]:
            try:
                profile.watched.add(Project.objects.get(slug=subscription))
            except Project.DoesNotExist:
                continue

    @staticmethod
    def update_languages(profile, userprofile) -> None:
        """Update user language preferences."""
        profile.language = userprofile["language"]
        for lang in userprofile["secondary_languages"]:
            profile.secondary_languages.add(Language.objects.auto_get_or_create(lang))
        for lang in userprofile["languages"]:
            profile.languages.add(Language.objects.auto_get_or_create(lang))

    def handle_compat(self, data) -> None:
        """Compatibility with pre 3.6 dumps."""
        if "basic" in data:
            return
        data["basic"] = {"username": data["username"]}
        data["profile"] = {
            "translated": data["translated"],
            "suggested": data["suggested"],
            "language": data["language"],
            "uploaded": data.get("uploaded", 0),
            "secondary_languages": data["secondary_languages"],
            "languages": data["languages"],
            "watched": data["subscriptions"],
        }

    def handle(self, **options) -> None:
        """
        Create default set of groups.

        Also ptionally updates them and moves users around to default group.
        """
        userdata = json.load(options["json-file"])
        options["json-file"].close()

        for userprofile in userdata:
            self.handle_compat(userprofile)
            username = userprofile["basic"]["username"]
            try:
                user = User.objects.get(username=username)
                update = False
                profile = user.profile
                if not profile.language:
                    update = True

                # Merge stats
                profile.translated += userprofile["profile"]["translated"]
                profile.suggested += userprofile["profile"]["suggested"]
                profile.uploaded += userprofile["profile"]["uploaded"]

                # Update fields if we should
                if update:
                    self.update_languages(profile, userprofile["profile"])

                # Add subscriptions
                self.import_watched(profile, userprofile["profile"])

                profile.save()
            except User.DoesNotExist:
                self.stderr.write(f"User not found: {username}\n")
