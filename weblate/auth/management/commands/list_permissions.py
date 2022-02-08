#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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
        self.stdout.write("Managing per-project access control\n\n")

        for name in ACL_GROUPS:
            self.stdout.write(f"{name}\n\n\n")

        self.stdout.write("\n\n")

        last = ""

        table = []
        rows = []

        for key, name in PERMISSIONS:
            base = key.split(".")[0]
            if base != last:
                if last:
                    table.append((PERM_NAMES[last], rows))
                last = base
                rows = []

            rows.append(
                (
                    name,
                    ", ".join(
                        f"`{name}`" for name, permissions in ROLES if key in permissions
                    ),
                )
            )
        table.append((PERM_NAMES[last], rows))

        rows = [(name, "") for _key, name in GLOBAL_PERMISSIONS]
        table.append(("Site wide privileges", rows))

        len_1 = max(len(group) for group, _rows in table)
        len_2 = max(len(name) for _group, rows in table for name, _role in rows)
        len_3 = max(len(role) for _group, rows in table for _name, role in rows)

        sep = f"+-{'-' * len_1}-+-{'-' * len_2}-+-{'-' * len_3}-+"
        blank_sep = f"+ {' ' * len_1} +-{'-' * len_2}-+-{'-' * len_3}-+"
        row = f"| {{:{len_1}}} | {{:{len_2}}} | {{:{len_3}}} |"
        self.stdout.write(sep)
        self.stdout.write(row.format("Scope", "Permission", "Roles"))
        self.stdout.write(sep.replace("-", "="))
        for scope, rows in table:
            number = 0
            for name, role in rows:
                if number:
                    self.stdout.write(blank_sep)
                self.stdout.write(row.format(scope if number == 0 else "", name, role))
                number += 1
            self.stdout.write(sep)
