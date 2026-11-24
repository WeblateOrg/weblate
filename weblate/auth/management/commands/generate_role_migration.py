# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import inspect
from importlib import import_module
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING

from django.core.management.base import CommandError
from django.db.migrations.loader import MigrationLoader

from weblate.auth.data import GLOBAL_PERMISSIONS, PERMISSIONS, ROLES
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "Generate a frozen three-way merge migration for built-in role defaults."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--check", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        loader = MigrationLoader(None)
        leaves = loader.graph.leaf_nodes("weblate_auth")
        if len(leaves) != 1:
            msg = "Merge the auth migration branches first."
            raise CommandError(msg)
        leaf = leaves[0][1]
        snapshots = [
            import_module(loader.disk_migrations[app, name].__module__)
            for app, name in loader.graph.forwards_plan(leaves[0])
            if app == "weblate_auth"
        ]
        previous = [module for module in snapshots if hasattr(module, "NEW_DEFAULTS")][
            -1
        ]
        current = {name: sorted(perms) for name, perms in sorted(ROLES)}
        if current == previous.NEW_DEFAULTS:
            self.stdout.write("Built-in role migrations are up to date.")
            return
        if options["check"]:
            msg = "Built-in role defaults changed; run generate_role_migration."
            raise CommandError(msg)
        number = int(leaf.split("_", 1)[0]) + 1
        if previous.__file__ is None:
            msg = "The previous role migration has no source file."
            raise CommandError(msg)
        source = Path(previous.__file__)
        target = source.with_name(f"{number:04d}_update_builtin_roles.py")
        header = (
            source.read_text(encoding="utf-8").split("\nOLD_DEFAULTS", 1)[0] + "\n\n"
        )
        content = header
        content += (
            "OLD_DEFAULTS: dict[str, list[str]] = "
            + pformat(previous.NEW_DEFAULTS)
            + "\n\n"
        )
        content += "NEW_DEFAULTS = " + pformat(current) + "\n\n"
        content += (
            "PERMISSION_LABELS = "
            + pformat(dict(sorted((*PERMISSIONS, *GLOBAL_PERMISSIONS))))
            + "\n\n\n"
        )
        content += inspect.getsource(previous.merge_roles)
        content += (
            "\n\nclass Migration(migrations.Migration):\n"
            f"    dependencies = [('weblate_auth', {leaf!r})]\n\n"
            "    operations = [migrations.RunPython(merge_roles)]\n"
        )
        with target.open("x", encoding="utf-8") as output:
            output.write(content)
        self.stdout.write(str(target))
