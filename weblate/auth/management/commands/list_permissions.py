# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.auth.data import ACL_GROUPS, GLOBAL_PERMISSIONS, GROUPS, PERMISSIONS, ROLES
from weblate.utils.management.base import BaseCommand
from weblate.utils.rst import format_table

GROUP_NAMES = {
    "announcement": "Announcements",
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

PERMISSION_NAMES = dict(GLOBAL_PERMISSIONS)
PERMISSION_NAMES.update(PERMISSIONS)


class Command(BaseCommand):
    help = "List permissions"

    def handle(self, *args, **options) -> None:
        """List permissions."""
        self.stdout.write("""
Managing per-project access control
-----------------------------------

..
   Partly generated using ./manage.py list_permissions

""")

        for name in ACL_GROUPS:
            self.stdout.write(f"`{name}`\n\n\n")

        self.stdout.write("""
List of privileges
++++++++++++++++++

..
   Generated using ./manage.py list_permissions

""")

        last = ""

        table: list[list[str | list[list[str]]]] = []
        rows: list[list[str]] = []

        for key, name in PERMISSIONS:
            base = key.split(".")[0]
            if base != last:
                if last:
                    table.append([GROUP_NAMES[last], rows])
                last = base
                rows = []

            rows.append(
                [
                    name,
                    ", ".join(
                        f":guilabel:`{name}`"
                        for name, permissions in ROLES
                        if key in permissions
                    ),
                ]
            )
        table.append([GROUP_NAMES[last], rows])

        rows = [
            [
                name,
                ", ".join(
                    f":guilabel:`{name}`"
                    for name, permissions in ROLES
                    if key in permissions
                ),
            ]
            for key, name in GLOBAL_PERMISSIONS
        ]
        table.append(["Site wide privileges", rows])

        self.stdout.writelines(
            format_table(table, ["Scope", "Permission", "Built-in roles"])
        )

        self.stdout.write("""
List of built-in roles
++++++++++++++++++++++

..
   Generated using ./manage.py list_permissions

""")

        self.stdout.write(".. list-table::\n\n")

        for name, permissions in ROLES:
            self.stdout.write(f"   * - `{name}`")
            self.stdout.write("     - ", ending="")
            self.stdout.write(
                "\n       ".join(
                    f"* :guilabel:`{PERMISSION_NAMES[perm]}`"
                    for perm in sorted(permissions)
                )
            )

        self.stdout.write("""
List of teams
+++++++++++++

""")

        for name, roles, _selection in GROUPS:
            self.stdout.write(f"`{name}`\n\n\n")
            if not roles:
                roles_str = "none"
            else:
                roles_str = ", ".join(f"`{role}`" for role in roles)
            self.stdout.write(f"    Default roles: {roles_str}\n\n")
