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

    def add_arguments(self, parser):
        parser.add_argument(
            "--sections",
            nargs="*",
            choices=["acl", "perms", "roles", "teams"],
            help="Filter output by section. Can specify multiple sections. "
            "If not specified, all sections are shown.",
        )

    def handle(self, *args, **options) -> None:
        """List permissions."""
        sections = set(options.get("sections", []) or [])
        show_all = not sections

        if show_all or "acl" in sections:
            self.write_acl()

        if show_all or "perms" in sections:
            self.write_perms()

        if show_all or "roles" in sections:
            self.write_roles()

        if show_all or "teams" in sections:
            self.write_teams()

    def write_acl(self) -> None:
        """Write access control section."""
        self.stdout.write("""
Managing per-project access control
-----------------------------------

..
   Partly generated using ./manage.py list_permissions

""")

        for name in ACL_GROUPS:
            self.stdout.write(f"`{name}`\n\n\n")

    def write_perms(self) -> None:
        """Write permissions section."""
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
                    [
                        [f":guilabel:`{name}`"]
                        for name, permissions in ROLES
                        if key in permissions
                    ],
                ]
            )
        # Fill in blank tables when there is no role
        for row in rows:
            if len(row[1]) == 0:
                row[1].append([""])
        table.append([GROUP_NAMES[last], rows])

        rows = [
            [
                name,
                [
                    [f":guilabel:`{name}`"]
                    for name, permissions in ROLES
                    if key in permissions
                ],
            ]
            for key, name in GLOBAL_PERMISSIONS
        ]
        # Fill in blank tables when there is no role
        for row in rows:
            if len(row[1]) == 0:
                row[1].append([""])
        table.append(["Site wide privileges", rows])

        self.stdout.writelines(
            format_table(table, ["Scope", "Permission", "Built-in roles"])
        )

    def write_roles(self) -> None:
        """Write roles section."""
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
            self.stdout.write("\n")

    def write_teams(self) -> None:
        """Write teams section."""
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
