# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import json

from weblate.auth.models import User
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "imports users from JSON dump of database"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Only check import, do not actually create users",
        )
        parser.add_argument(
            "json-file",
            type=argparse.FileType("r"),
            help="JSON file containing user dump to import",
        )

    def handle(self, *args, **options) -> None:
        data = json.load(options["json-file"])
        options["json-file"].close()

        for line in data:
            if "fields" in line:
                line = line["fields"]

            if "is_active" in line and not line["is_active"]:
                continue

            username = line["username"]
            email = line["email"]

            if not email or not username:
                self.stderr.write(f"Skipping {line}, has blank username or email")
                continue

            if User.objects.filter(username=username).exists():
                self.stderr.write(f"Skipping {username}, username exists")
                continue

            if User.objects.filter(email=email).exists():
                self.stderr.write(f"Skipping {email}, email exists")
                continue

            last_name = line.get("last_name", "")
            first_name = line.get("first_name", "")
            if last_name and last_name not in first_name:
                full_name = f"{first_name} {last_name}"
            elif first_name:
                full_name = first_name
            elif last_name:
                full_name = last_name
            else:
                full_name = username

            if not options["check"]:
                User.objects.create(
                    username=username,
                    full_name=full_name,
                    password=line.get("password", ""),
                    email=email,
                )
