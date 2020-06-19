#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from weblate.auth.models import User
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "imports users from JSON dump of database"

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        data = json.load(options["json-file"])
        options["json-file"].close()

        for line in data:
            if "fields" in line:
                line = line["fields"]

            if "is_active" in line and not line["is_active"]:
                continue

            if not line["email"] or not line["username"]:
                self.stderr.write(
                    "Skipping {0}, has blank username or email".format(line)
                )
                continue

            if User.objects.filter(username=line["username"]).exists():
                self.stderr.write(
                    "Skipping {0}, username exists".format(line["username"])
                )
                continue

            if User.objects.filter(email=line["email"]).exists():
                self.stderr.write("Skipping {0}, email exists".format(line["email"]))
                continue

            if line["last_name"] not in line["first_name"]:
                full_name = "{0} {1}".format(line["first_name"], line["last_name"])
            elif line.get("first_name"):
                full_name = line["first_name"]
            else:
                full_name = line["username"]

            if not options["check"]:
                User.objects.create(
                    username=line["username"],
                    full_name=full_name,
                    password=line.get("password", ""),
                    email=line["email"],
                )
