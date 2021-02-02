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

from weblate.auth.data import ACL_GROUPS, GLOBAL_PERMISSIONS, PERMISSIONS, ROLES
from weblate.utils.management.base import BaseCommand

PERM_NAMES = {
    "billing": "Billing (see :ref:`billing`)",
    "change": "Changes",
    "comment": "Comments",
    "component": "Component",
    "glossary": "Glossary",
    "machinery": "Automatic suggestions",
    "memory": "Translation memory",
    "project": "Projects",
    "reports": "Reports",
    "screenshot": "Screenshots",
    "source": "Source strings",
    "suggestion": "Suggestions",
    "translation": "Translations",
    "upload": "Uploads",
    "unit": "Strings",
    "vcs": "VCS",
}


class Command(BaseCommand):
    help = "List permissions"

    def handle(self, *args, **options):
        """List permissions."""
        for name in ACL_GROUPS:
            self.stdout.write(f".. describe:: {name}\n\n\n")

        self.stdout.write("\n\n")

        last = ""

        for key, name in PERMISSIONS:
            base = key.split(".")[0]
            if base != last:
                self.stdout.write(PERM_NAMES[base])
                last = base
            roles = "`, `".join(
                [name for name, permissions in ROLES if key in permissions]
            )
            self.stdout.write(f"    {name} [`{roles}`]")
            self.stdout.write("\n")

        self.stdout.write("Site wide privileges")
        for _key, name in GLOBAL_PERMISSIONS:
            self.stdout.write(f"    {name}\n\n")
